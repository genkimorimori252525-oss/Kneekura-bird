package com.wwdebug.gametestprobe;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

/** Harmless classpath probe; this class is not an instrument or a GameTest. */
public final class ClasspathMarker {
    private ClasspathMarker() {}

    public static String value() {
        return "game-test-only";
    }

    public static void main(String[] args) throws IOException {
        try (var stream = ClasspathMarker.class.getClassLoader()
                .getResourceAsStream("wwdebug-gametest-only.marker")) {
            if (stream == null || !value().equals(new String(stream.readAllBytes(), StandardCharsets.UTF_8).trim())) {
                throw new IllegalStateException("GameTest-only marker resource is unavailable");
            }
        }
        System.out.println(value());
    }
}
