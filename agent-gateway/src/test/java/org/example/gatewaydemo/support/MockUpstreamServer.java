package org.example.gatewaydemo.support;

import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import java.io.IOException;

/**
 * 本地 Mock 上游，避免集成测试依赖外网 httpbin。
 */
public final class MockUpstreamServer {

    private static MockWebServer server;

    private MockUpstreamServer() {
    }

    public static void start() throws IOException {
        if (server != null) {
            return;
        }
        server = new MockWebServer();
        server.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest request) {
                String path = request.getPath() == null ? "" : request.getPath();
                if (path.startsWith("/get")) {
                    return json(200, "{\"origin\":\"mock\"}");
                }
                if (path.startsWith("/post")) {
                    return json(200, "{\"url\":\"mock/post\"}");
                }
                if (path.startsWith("/llm")) {
                    String largeContent = "y".repeat(500);
                    String body = """
                            {"choices":[{"message":{"content":"%s"}}],\
                            "usage":{"prompt_tokens":10,"completion_tokens":200,"total_tokens":210}}\
                            """.formatted(largeContent);
                    return json(200, body);
                }
                if (path.startsWith("/health")) {
                    return json(200, "{\"status\":\"ok\",\"collection\":\"test\"}");
                }
                if (path.startsWith("/api/chat/stream")) {
                    String largeContent = "y".repeat(500);
                    String sse = """
                            event: token
                            data: {"content":"%s"}
                            
                            event: done
                            data: {"content":"%s","rewritten_query":"hi"}
                            
                            """.formatted(largeContent, largeContent);
                    return new MockResponse()
                            .setResponseCode(200)
                            .addHeader("Content-Type", "text/event-stream")
                            .setBody(sse);
                }
                return new MockResponse().setResponseCode(404);
            }
        });
        server.start();
    }

    public static void shutdown() throws IOException {
        if (server != null) {
            server.shutdown();
            server = null;
        }
    }

    public static int getPort() {
        if (server == null) {
            throw new IllegalStateException("MockWebServer not started");
        }
        return server.getPort();
    }

    private static MockResponse json(int code, String body) {
        return new MockResponse()
                .setResponseCode(code)
                .addHeader("Content-Type", "application/json")
                .setBody(body);
    }
}
