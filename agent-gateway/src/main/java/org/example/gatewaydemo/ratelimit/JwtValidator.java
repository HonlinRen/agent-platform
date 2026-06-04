package org.example.gatewaydemo.ratelimit;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

/** 轻量 JWT HS256 校验（Demo）。 */
public final class JwtValidator {

    private JwtValidator() {
    }

    public static String extractSubject(String token, String secret) {
        if (token == null || token.isBlank()) {
            throw new IllegalArgumentException("missing token");
        }
        String[] parts = token.trim().split("\\.");
        if (parts.length != 3) {
            throw new IllegalArgumentException("invalid jwt format");
        }
        verifySignature(parts[0], parts[1], parts[2], secret);
        String payloadJson = new String(Base64.getUrlDecoder().decode(parts[1]), StandardCharsets.UTF_8);
        String sub = extractJsonString(payloadJson, "sub");
        if (sub == null || sub.isBlank()) {
            throw new IllegalArgumentException("missing sub claim");
        }
        return sub;
    }

    private static void verifySignature(String header, String payload, String signature, String secret) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            byte[] expected = mac.doFinal((header + "." + payload).getBytes(StandardCharsets.UTF_8));
            byte[] actual = Base64.getUrlDecoder().decode(signature);
            if (!constantTimeEquals(expected, actual)) {
                throw new IllegalArgumentException("invalid signature");
            }
        } catch (IllegalArgumentException ex) {
            throw ex;
        } catch (Exception ex) {
            throw new IllegalArgumentException("signature verification failed", ex);
        }
    }

    private static boolean constantTimeEquals(byte[] a, byte[] b) {
        if (a.length != b.length) {
            return false;
        }
        int result = 0;
        for (int i = 0; i < a.length; i++) {
            result |= a[i] ^ b[i];
        }
        return result == 0;
    }

    private static String extractJsonString(String json, String key) {
        String pattern = "\"" + key + "\":\"";
        int start = json.indexOf(pattern);
        if (start < 0) {
            return null;
        }
        start += pattern.length();
        int end = json.indexOf('"', start);
        if (end < 0) {
            return null;
        }
        return json.substring(start, end);
    }
}
