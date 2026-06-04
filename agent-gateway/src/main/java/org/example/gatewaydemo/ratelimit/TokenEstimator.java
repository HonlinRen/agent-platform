package org.example.gatewaydemo.ratelimit;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import org.springframework.http.MediaType;
import org.springframework.util.StringUtils;

import java.nio.charset.StandardCharsets;
/**
 * OpenAI 兼容 API 的 Token 估算：优先读 usage 字段，否则按字符数 / 4 粗算。
 */
public final class TokenEstimator {

    private static final JsonMapper MAPPER = JsonMapper.builder().build();
    private static final int CHARS_PER_TOKEN = 4;

    private TokenEstimator() {
    }

    /** 解析 chat/completions 请求体：优先 messages[].content，否则整段 UTF-8 按 len/4 估算 */
    public static long estimateInputTokens(byte[] body) {
        if (body == null || body.length == 0) {
            return 1L;
        }
        try {
            JsonNode root = MAPPER.readTree(body);
            long fromMessages = sumMessageContentTokens(root.get("messages"));
            if (fromMessages > 0) {
                return Math.max(1L, fromMessages);
            }
            long fromChatStream = sumChatStreamTokens(root);
            if (fromChatStream > 0) {
                return Math.max(1L, fromChatStream);
            }
            JsonNode input = root.get("input");
            if (input != null) {
                return estimateTextTokens(input.asText(""));
            }
            return estimateTextTokens(new String(body, StandardCharsets.UTF_8));
        } catch (Exception ignored) {
            return Math.max(1L, body.length / CHARS_PER_TOKEN);
        }
    }

    public record OutputChunkResult(long tokensToConsume, boolean usageFromApi) {
    }

    /** 响应分片：SSE 解析 data: 行；非 SSE 解析 usage.completion_tokens 或 choices[0].message */
    public static OutputChunkResult parseOutputChunk(byte[] chunk, MediaType contentType) {
        if (chunk == null || chunk.length == 0) {
            return new OutputChunkResult(0L, false);
        }
        String text = new String(chunk, StandardCharsets.UTF_8);
        boolean sse = contentType != null && MediaType.TEXT_EVENT_STREAM.isCompatibleWith(contentType);

        if (sse) {
            return parseSseChunk(text);
        }
        return parseJsonBody(text);
    }

    private static OutputChunkResult parseSseChunk(String text) {
        long deltaTokens = 0L;
        Long totalFromDone = null;
        String currentEvent = null;

        for (String line : text.split("\n")) {
            if (line.startsWith("event:")) {
                currentEvent = line.substring(6).trim();
                continue;
            }
            if (!line.startsWith("data:")) {
                continue;
            }
            String payload = line.substring(5).trim();
            if (!StringUtils.hasText(payload) || "[DONE]".equals(payload)) {
                continue;
            }
            try {
                JsonNode node = MAPPER.readTree(payload);
                JsonNode usage = node.get("usage");
                if (usage != null && usage.has("completion_tokens")) {
                    totalFromDone = usage.get("completion_tokens").asLong();
                }
                JsonNode choices = node.get("choices");
                if (choices != null && choices.isArray()) {
                    for (JsonNode choice : choices) {
                        JsonNode delta = choice.get("delta");
                        if (delta != null && delta.has("content")) {
                            deltaTokens += estimateTextTokens(delta.get("content").asText(""));
                        }
                        JsonNode message = choice.get("message");
                        if (message != null && message.has("content")) {
                            deltaTokens += estimateTextTokens(message.get("content").asText(""));
                        }
                    }
                }
                JsonNode content = node.get("content");
                if (content != null && content.isTextual()) {
                    if ("done".equals(currentEvent)) {
                        totalFromDone = estimateTextTokens(content.asText(""));
                    } else {
                        deltaTokens += estimateTextTokens(content.asText(""));
                    }
                }
            } catch (Exception ignored) {
                deltaTokens += estimateTextTokens(payload);
            }
        }

        if (totalFromDone != null) {
            return new OutputChunkResult(totalFromDone, true);
        }
        return new OutputChunkResult(deltaTokens, false);
    }

    private static OutputChunkResult parseJsonBody(String text) {
        try {
            JsonNode root = MAPPER.readTree(text);
            JsonNode usage = root.get("usage");
            if (usage != null) {
                if (usage.has("completion_tokens")) {
                    return new OutputChunkResult(usage.get("completion_tokens").asLong(), true);
                }
                if (usage.has("total_tokens") && usage.has("prompt_tokens")) {
                    long total = usage.get("total_tokens").asLong();
                    long prompt = usage.get("prompt_tokens").asLong();
                    return new OutputChunkResult(Math.max(0L, total - prompt), true);
                }
            }
            JsonNode choices = root.get("choices");
            if (choices != null && choices.isArray() && !choices.isEmpty()) {
                JsonNode message = choices.get(0).get("message");
                if (message != null && message.has("content")) {
                    return new OutputChunkResult(estimateTextTokens(message.get("content").asText("")), false);
                }
            }
        } catch (Exception ignored) {
            // fall through
        }
        return new OutputChunkResult(estimateTextTokens(text), false);
    }

    private static long sumMessageContentTokens(JsonNode messages) {
        if (messages == null || !messages.isArray()) {
            return 0L;
        }
        long total = 0L;
        for (JsonNode message : messages) {
            JsonNode content = message.get("content");
            if (content == null) {
                continue;
            }
            if (content.isTextual()) {
                total += estimateTextTokens(content.asText());
            } else if (content.isArray()) {
                for (JsonNode part : content) {
                    if (part.has("text")) {
                        total += estimateTextTokens(part.get("text").asText(""));
                    }
                }
            }
        }
        return total;
    }

    /** agent-rag ChatStreamRequest：message + history[].content */
    private static long sumChatStreamTokens(JsonNode root) {
        if (root == null) {
            return 0L;
        }
        long total = 0L;
        JsonNode message = root.get("message");
        if (message != null && message.isTextual()) {
            total += estimateTextTokens(message.asText());
        }
        JsonNode history = root.get("history");
        if (history != null && history.isArray()) {
            for (JsonNode item : history) {
                JsonNode content = item.get("content");
                if (content != null && content.isTextual()) {
                    total += estimateTextTokens(content.asText());
                }
            }
        }
        return total;
    }

    private static long estimateTextTokens(String text) {
        if (!StringUtils.hasText(text)) {
            return 0L;
        }
        return Math.max(1L, text.length() / CHARS_PER_TOKEN);
    }

    public static byte[] readBytesAndRelease(org.springframework.core.io.buffer.DataBuffer buffer) {
        try {
            byte[] bytes = new byte[buffer.readableByteCount()];
            buffer.read(bytes);
            return bytes;
        } finally {
            org.springframework.core.io.buffer.DataBufferUtils.release(buffer);
        }
    }
}
