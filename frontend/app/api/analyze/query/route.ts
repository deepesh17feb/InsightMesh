import { NextRequest, NextResponse } from "next/server";
import { BACKEND_URL } from "../../../backend-url";

export const maxDuration = 60;

export async function POST(req: NextRequest) {
  try {
    const { question } = await req.json();

    const response = await fetch(`${BACKEND_URL}/api/analyze/query`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        question,
        spec_id: "chat",
      }),
    });

    if (!response.ok) {
      const errText = await response.text();
      return NextResponse.json(
        { error: `Backend returned ${response.status}: ${errText}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error: any) {
    console.error("API analyze proxy error:", error);
    return NextResponse.json(
      { error: error.message || "Failed to contact InsightMesh backend" },
      { status: 500 }
    );
  }
}
