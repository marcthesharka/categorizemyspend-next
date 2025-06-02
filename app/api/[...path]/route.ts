import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest) {
  const path = request.nextUrl.pathname.replace('/api/', '');
  const searchParams = request.nextUrl.searchParams.toString();
  const url = `${process.env.PYTHON_API_URL || 'http://localhost:5000'}/${path}${searchParams ? `?${searchParams}` : ''}`;
  
  try {
    const response = await fetch(url);
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json({ error: 'Failed to fetch from Python API' }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  const path = request.nextUrl.pathname.replace('/api/', '');
  const url = `${process.env.PYTHON_API_URL || 'http://localhost:5000'}/${path}`;
  
  try {
    if (path === 'categorize') {
      const formData = await request.formData();
      const files = formData.getAll('pdf');
      
      if (!files || files.length === 0) {
        return NextResponse.json({ error: 'No PDF files provided' }, { status: 400 });
      }

      const results = [];
      for (const file of files) {
        if (file instanceof File) {
          const buffer = await file.arrayBuffer();
          const base64 = Buffer.from(buffer).toString('base64');
          
          const response = await fetch(url, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({ pdf_data: base64 }),
          });
          
          if (!response.ok) {
            throw new Error(`Failed to process PDF: ${response.statusText}`);
          }
          
          const data = await response.json();
          results.push(...data);
        }
      }
      
      return NextResponse.json(results);
    } else {
      const body = await request.json();
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      });
      const data = await response.json();
      return NextResponse.json(data);
    }
  } catch (error) {
    console.error('API error:', error);
    return NextResponse.json({ error: 'Failed to process request' }, { status: 500 });
  }
} 