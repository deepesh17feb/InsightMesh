import { NextRequest, NextResponse } from "next/server";
import { BACKEND_URL } from "../../backend-url";

export const maxDuration = 60;

export async function POST(req: NextRequest) {
  try {
    const { messages, model } = await req.json();

    const response = await fetch(`${BACKEND_URL}/v1/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: model || "atlys-instrumentation",
        messages,
        stream: true,
      }),
    });

    if (!response.ok) {
      const errText = await response.text();
      return NextResponse.json(
        { error: `Backend returned ${response.status}: ${errText}` },
        { status: response.status }
      );
    }

    // Stream SSE directly to the browser
    return new Response(response.body, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  } catch (error: any) {
    console.error("API Chat proxy error:", error);
    return NextResponse.json(
      { error: error.message || "Failed to contact InsightMesh backend" },
      { status: 500 }
    );
  }
}
