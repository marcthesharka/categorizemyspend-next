import os
import tempfile
import json
import pdfplumber
import pandas as pd
from datetime import datetime, date
import openai
import stripe
from http.server import BaseHTTPRequestHandler
from typing import Dict, List, Any

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

def parse_pdf_transactions(pdf_path: str) -> List[Dict[str, Any]]:
    import re
    from datetime import datetime
    with pdfplumber.open(pdf_path) as pdf:
        first_page_text = pdf.pages[0].extract_text() or ""
        if "Chase" in first_page_text:
            return parse_chase_pdf_transactions(pdf_path)
        elif "Apple Card" in first_page_text:
            return parse_apple_pdf_transactions(pdf_path)
        elif "Capital One" in first_page_text:
            return parse_capitalone_pdf_transactions(pdf_path)
        elif "American Express" in first_page_text or "americanexpress.com" in first_page_text:
            return parse_amex_pdf_transactions(pdf_path)
        else:
            raise ValueError("Unknown statement format")

def parse_chase_pdf_transactions(pdf_path: str) -> List[Dict[str, Any]]:
    import re
    from datetime import datetime, date, timedelta
    transactions = []
    in_transactions_section = False
    today = date.today()
    with pdfplumber.open(pdf_path) as pdf:
        print(f"PDF has {len(pdf.pages)} pages (Chase)")
        for i, page in enumerate(pdf.pages[2:], start=3):  # skip first two pages
            text = page.extract_text()
            if not text:
                continue
            lines = text.splitlines()
            for line in lines:
                if "payments and other credits" in line.lower() or "purchase" in line.lower():
                    in_transactions_section = True
                    continue
                if "account activity" in line.lower():
                    continue
                if not in_transactions_section:
                    continue
                if "totals year-to-date" in line.lower() or "interest charges" in line.lower():
                    in_transactions_section = False
                    break
                if line.strip() == "" or "date of" in line.lower() or "merchant name" in line.lower() or "description" in line.lower() or "amount" in line.lower():
                    continue
                match = re.match(r"^(\d{2}/\d{2})\s+(.+?)\s+(-?\$?[\d,]*\.\d{2})$", line)
                if match:
                    date_str, desc, amount_str = match.groups()
                    try:
                        year = today.year
                        parsed_date = datetime.strptime(f"{date_str}/{year}", "%m/%d/%Y").date()
                        if parsed_date > today:
                            parsed_date = parsed_date.replace(year=year-1)
                        date_obj = datetime.combine(parsed_date, datetime.min.time())
                        amount = float(amount_str.replace('$', '').replace(',', ''))
                        if amount is None:
                            amount = 0.0
                        transactions.append({
                            'date': date_obj,
                            'description': desc.strip(),
                            'amount': amount,
                            'category': '',
                            'card': 'Chase'
                        })
                    except Exception as e:
                        print(f"Error parsing Chase line: {line} -- {e}")
                        continue
    print(f"Total Chase transactions found: {len(transactions)}")
    return transactions

def parse_apple_pdf_transactions(pdf_path: str) -> List[Dict[str, Any]]:
    import re
    from datetime import datetime, date, timedelta
    transactions = []
    today = date.today()
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[1:]:  # Skip first page
            text = page.extract_text()
            if not text:
                continue
            lines = text.splitlines()
            in_transactions = False
            for line in lines:
                if "Transactions" in line:
                    in_transactions = True
                    continue
                if not in_transactions:
                    continue
                if line.strip() == "" or "Date" in line or "Description" in line or "Amount" in line or "Daily Cash" in line:
                    continue
                match = re.match(r"^(\d{2}/\d{2}/\d{4})\s+(.+?)\s+\d+%\s+\$[\d,.]+\s+(-?\$[\d,.]+)$", line)
                if match:
                    date_str, desc, amount_str = match.groups()
                    try:
                        parsed_date = datetime.strptime(date_str, "%m/%d/%Y").date()
                        if parsed_date > today:
                            parsed_date = parsed_date.replace(year=parsed_date.year-1)
                        date_obj = datetime.combine(parsed_date, datetime.min.time())
                        amount = float(amount_str.replace('$', '').replace(',', ''))
                        if amount is None:
                            amount = 0.0
                        transactions.append({
                            'date': date_obj,
                            'description': desc.strip(),
                            'amount': amount,
                            'category': '',
                            'card': 'Apple Card'
                        })
                    except Exception as e:
                        print(f"Error parsing Apple Card line: {line} -- {e}")
                        continue
    print(f"Total Apple Card transactions found: {len(transactions)}")
    return transactions

def parse_capitalone_pdf_transactions(pdf_path: str) -> List[Dict[str, Any]]:
    import re
    from datetime import datetime, date
    transactions = []
    today = date.today()
    in_transactions_section = False
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages[2:], start=3):  # skip first two pages
            text = page.extract_text()
            if not text:
                continue
            lines = text.splitlines()
            for line in lines:
                # Start parsing when we hit the Transactions section
                if "Transactions" in line and not in_transactions_section:
                    in_transactions_section = True
                    continue
                if not in_transactions_section:
                    continue
                # Stop if we hit Fees or Interest or end of transactions
                if "Fees" in line or "Interest Charged" in line or "Total Transactions for This Period" in line:
                    in_transactions_section = False
                    break
                # Skip headers and empty lines
                if line.strip() == "" or "Trans Date" in line or "Description" in line or "Amount" in line or "Post Date" in line:
                    continue
                # Match lines like: Mar 14   H MARTNEW YORKNY   $8.33
                match = re.match(r"^([A-Za-z]{3} \d{1,2})\s+(.+?)\s+\$?(-?[\d,]+\.\d{2})$", line)
                if match:
                    date_str, desc, amount_str = match.groups()
                    try:
                        # Parse date (assume current year, adjust if in future)
                        year = today.year
                        parsed_date = datetime.strptime(f"{date_str} {year}", "%b %d %Y").date()
                        if parsed_date > today:
                            parsed_date = parsed_date.replace(year=year-1)
                        date_obj = datetime.combine(parsed_date, datetime.min.time())
                        amount = float(amount_str.replace(',', ''))
                        # Exclude repayments: description contains 'CAPITAL ONE AUTOPAY'
                        if 'CAPITAL ONE AUTOPAY' in desc.upper():
                            continue
                        if amount is None:
                            amount = 0.0
                        transactions.append({
                            'date': date_obj,
                            'description': desc.strip(),
                            'amount': amount,
                            'category': '',
                            'card': 'Capital One'
                        })
                    except Exception as e:
                        print(f"Error parsing Capital One line: {line} -- {e}")
                        continue
    print(f"Total Capital One transactions found: {len(transactions)}")
    return transactions

def parse_amex_pdf_transactions(pdf_path: str) -> List[Dict[str, Any]]:
    import re
    from datetime import datetime, date
    transactions = []
    today = date.today()
    in_transactions_section = False
    current_txn = None
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages[2:], start=3):  # skip first two pages
            text = page.extract_text()
            if not text:
                continue
            lines = text.splitlines()
            for idx, line in enumerate(lines):
                # Start parsing at 'Card Ending'
                if not in_transactions_section and 'Card Ending' in line:
                    in_transactions_section = True
                    continue
                if not in_transactions_section:
                    continue
                # Stop at 'Fees'
                if 'Fees' in line:
                    # Save the last transaction if any
                    if current_txn:
                        # Only append if not AUTOPAY PAYMENT RECEIVED
                        if not (current_txn['description'].strip().upper().startswith('AUTOPAY PAYMENT RECEIVED')):
                            transactions.append(current_txn)
                        current_txn = None
                    in_transactions_section = False
                    break
                # Match a line that starts with a date (MM/DD/YY or MM/DD/YYYY)
                date_match = re.match(r'^(\d{2}/\d{2}/\d{2,4})\*?\s+(.*)', line)
                if date_match:
                    # Save the previous transaction if any
                    if current_txn:
                        # Only append if not AUTOPAY PAYMENT RECEIVED
                        if not (current_txn['description'].strip().upper().startswith('AUTOPAY PAYMENT RECEIVED')):
                            transactions.append(current_txn)
                    date_str, rest = date_match.groups()
                    # Try to parse the date
                    try:
                        try:
                            parsed_date = datetime.strptime(date_str, "%m/%d/%y").date()
                        except ValueError:
                            parsed_date = datetime.strptime(date_str, "%m/%d/%Y").date()
                        if parsed_date > today:
                            parsed_date = parsed_date.replace(year=parsed_date.year - 1)
                        date_obj = datetime.combine(parsed_date, datetime.min.time())
                    except Exception:
                        date_obj = None
                    # Try to extract amount from the end of the line
                    amount_match = re.search(r'(\$?-?[\d,]+\.\d{2})[^\d]*$', rest)
                    if amount_match:
                        amount_str = amount_match.group(1)
                        amount_str = re.sub(r'[^\d\.\-,]', '', amount_str)
                        try:
                            amount = float(amount_str.replace('$', '').replace(',', ''))
                        except Exception:
                            amount = 0.0
                        # Remove the amount from the description
                        desc = rest[:amount_match.start()].strip()
                    else:
                        amount = None
                        desc = rest.strip()
                    current_txn = {
                        'date': date_obj,
                        'description': desc,
                        'amount': amount,
                        'category': '',
                        'card': 'American Express'
                    }
                else:
                    # If the line does not start with a date, it's a continuation of the previous transaction
                    if current_txn:
                        # Try to extract amount if this is the last line of a multi-line transaction
                        amount_match = re.search(r'(\$?-?[\d,]+\.\d{2})[^\d]*$', line)
                        if amount_match:
                            amount_str = amount_match.group(1)
                            amount_str = re.sub(r'[^\d\.\-,]', '', amount_str)
                            try:
                                amount = float(amount_str.replace('$', '').replace(',', ''))
                                current_txn['amount'] = amount
                            except Exception:
                                pass
                            # Remove the amount from the line before appending
                            line = line[:amount_match.start()].strip()
                        # Append the line to the description
                        if current_txn['description']:
                            current_txn['description'] += ' ' + line.strip()
                        else:
                            current_txn['description'] = line.strip()
    # Save the last transaction if any
    if current_txn:
        if not (current_txn['description'].strip().upper().startswith('AUTOPAY PAYMENT RECEIVED')):
            transactions.append(current_txn)
    print(f"Total American Express transactions found: {len(transactions)}")
    return transactions

def categorize_and_enhance_transaction(description: str) -> tuple[str, str]:
    # Special case for card repayment
    if description.strip().upper() == 'AUTOMATIC PAYMENT - THANK YOU':
        return 'Card Repayment', 'Credit card bill payment'
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    prompt = (
        f"Given this credit card transaction description: '{description}',\n"
        "1. Categorize it with one of the following, do not create new categories: 'Food & Beverage', 'Health & Wellness', 'Travel (Taxi / Uber / Lyft / Revel)', 'Travel (Subway / MTA)', 'Gas & Fuel','Travel (Flights / Trains)', 'Hotel', 'Groceries', 'Entertainment / Leisure Activities', 'Shopping', 'Income / Refunds', 'Utilities (Electricity, Telecom, Internet)', 'Other (Miscellaneous)'.\n"
        "2. Write a short, human-perceivable summary of the expense, including the merchant type and location if available. Follow the format: 'Merchant Name, Location, brief description of expense purpose (no more than 10 words)'\n"
        "Return your answer as JSON in the following format (no markdown, no explanation, just JSON):\n"
        '{"category": "...", "enhanced_description": "..."}'
    )
    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.3
        )
        content = response.choices[0].message.content.strip()
        print("OpenAI raw response:", content)  # Log for debugging
        # Try to extract JSON from the response
        try:
            data = json.loads(content)
        except Exception as e:
            print("JSON decode error:", e)
            # Try to extract JSON substring if extra text is present
            import re
            match = re.search(r'\\{.*\\}', content, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(0))
                except Exception as e2:
                    print("Still failed to parse JSON:", e2)
                    data = {}
            else:
                data = {}
        return data.get("category", "Uncategorized"), data.get("enhanced_description", description)
    except Exception as e:
        print(f"OpenAI error (combined): {e}")
        return "Uncategorized", description

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        if self.path == '/api/categorize':
            try:
                # Handle PDF file from base64
                pdf_data = data.get('pdf_data')
                if not pdf_data:
                    self.send_error(400, "No PDF data provided")
                    return
                
                # Save PDF to temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                    tmp.write(pdf_data.encode('utf-8'))
                    transactions = parse_pdf_transactions(tmp.name)
                    os.unlink(tmp.name)
                
                # Categorize transactions
                for transaction in transactions:
                    category, enhanced_desc = categorize_and_enhance_transaction(transaction['description'])
                    transaction['category'] = category
                    transaction['enhanced_description'] = enhanced_desc
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(transactions).encode())
                
            except Exception as e:
                self.send_error(500, str(e))
                
        elif self.path == '/api/create-payment-intent':
            try:
                num_pdfs = data.get('num_pdfs', 1)
                amount = num_pdfs * 200  # $2 per PDF, in cents
                
                intent = stripe.PaymentIntent.create(
                    amount=amount,
                    currency='usd',
                    automatic_payment_methods={'enabled': True},
                )
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'clientSecret': intent.client_secret}).encode())
                
            except Exception as e:
                self.send_error(500, str(e))
                
        else:
            self.send_error(404, "Endpoint not found")
    
    def do_GET(self):
        if self.path == '/api/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "healthy"}).encode())
        else:
            self.send_error(404, "Endpoint not found")

# Update the main block to work with Vercel
if __name__ == '__main__':
    from http.server import HTTPServer
    server_address = ('', 8080)
    httpd = HTTPServer(server_address, handler)
    httpd.serve_forever()