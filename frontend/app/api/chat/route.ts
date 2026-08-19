import { NextRequest, NextResponse } from "next/server";
import { BACKEND_URL } from "../../backend-url";

export const maxDuration = 60;

export async function POST(req: NextRequest) {
  try {
    const { messages, model } = await req.json();

    // Server-side only: authorizes HITL_APPROVE (production DDL execution)
    // through this proxy. Never exposed to the browser bundle.
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (process.env.INSIGHTMESH_API_KEY) {
      headers["x-api-key"] = process.env.INSIGHTMESH_API_KEY;
    }

    const response = await fetch(`${BACKEND_URL}/v1/chat/completions`, {
      method: "POST",
      headers,
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
