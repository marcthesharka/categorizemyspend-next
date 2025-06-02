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
  const body = await request.json();
  const url = `${process.env.PYTHON_API_URL || 'http://localhost:5000'}/${path}`;
  
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json({ error: 'Failed to fetch from Python API' }, { status: 500 });
  }
} 