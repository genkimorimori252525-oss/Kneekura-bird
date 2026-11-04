import java.io.*;
import java.net.*;
import java.nio.channels.*;
import java.nio.file.*;
import java.util.*;

/** Cooperating fixture only. Does not start Minecraft or contact an external service. */
public final class OwnedJavaProbe {
    static final LinkedHashMap<String,String> fields = new LinkedHashMap<>();
    static void put(String k, Object v) { fields.put(k, String.valueOf(v).replace('\n',' ')); }
    static String tcp(String address, int port) {
        try (Socket socket = new Socket(Proxy.NO_PROXY)) {
            socket.connect(new InetSocketAddress(InetAddress.getByName(address), port), 1000);
            return "CONNECTED";
        } catch (IOException ex) { return ex.getClass().getSimpleName() + ":" + ex.getMessage(); }
    }
    static String loopbackPositive(String address, int firstHostPort, int secondHostPort) {
        try {
            for (int attempt = 0; attempt < 10; attempt++) {
                try (ServerSocket server = new ServerSocket()) {
                    server.bind(new InetSocketAddress(InetAddress.getByName(address), 0));
                    int selected = server.getLocalPort();
                    if (selected == firstHostPort || selected == secondHostPort) continue;
                    server.setSoTimeout(1000);
                    try (Socket client = new Socket(Proxy.NO_PROXY)) {
                        client.connect(new InetSocketAddress(InetAddress.getByName(address), selected), 1000);
                        client.setSoTimeout(1000);
                        try (Socket accepted = server.accept()) {
                            accepted.setSoTimeout(1000);
                            client.getOutputStream().write(42);
                            return accepted.getInputStream().read() == 42 ? "PASS:port=" + selected : "WRONG_NONCE";
                        }
                    }
                }
            }
            return "COULD_NOT_SELECT_DISTINCT_PORT";
        } catch (IOException ex) { return ex.getClass().getSimpleName() + ":" + ex.getMessage(); }
    }
    public static void main(String[] args) throws Exception {
        put("runtime", Runtime.version());
        put("java_home", System.getProperty("java.home"));
        put("classpath", System.getProperty("java.class.path"));
        put("class_origin", OwnedJavaProbe.class.getProtectionDomain().getCodeSource().getLocation());
        try (InputStream in = OwnedJavaProbe.class.getResourceAsStream("/owned-resource.txt")) {
            if (in == null) throw new IOException("classpath resource missing");
            put("classpath_resource", new String(in.readAllBytes(), java.nio.charset.StandardCharsets.UTF_8).trim());
        }
        for (String name : List.of("net", "user", "mnt", "pid")) {
            put("namespace_" + name, Files.readSymbolicLink(Path.of("/proc/self/ns/" + name)));
        }
        for (String line : Files.readAllLines(Path.of("/proc/self/status"))) {
            if (line.startsWith("CapEff:") || line.startsWith("NoNewPrivs:") || line.startsWith("Seccomp:")) {
                put("process_" + line.substring(0, line.indexOf(':')), line.substring(line.indexOf(':') + 1).trim());
            }
        }
        Files.writeString(Path.of("/probe-output/mountinfo.txt"), Files.readString(Path.of("/proc/self/mountinfo")), StandardOpenOption.CREATE_NEW);
        put("workspace_visible", Files.exists(Path.of("/workspace")));
        put("run_visible", Files.exists(Path.of("/run")));
        put("parent_owned_marker_visible", Files.exists(Path.of(args[2])));
        put("parent_fd_visible", Files.exists(Path.of("/proc/" + args[3] + "/fd/" + args[4])));
        put("parent_root_visible", Files.exists(Path.of("/proc/" + args[3] + "/root" + args[2])));
        try (var channel = Files.newByteChannel(Path.of("/probe-input/owned-resource.txt"), StandardOpenOption.WRITE)) {
            put("readonly_open", "UNEXPECTED_ALLOWED");
        } catch (IOException ex) { put("readonly_open", ex.getClass().getSimpleName() + ":" + ex.getMessage()); }
        try (var channel = Files.newByteChannel(Path.of("/jdk/release"), StandardOpenOption.WRITE)) {
            put("jdk_readonly_open", "UNEXPECTED_ALLOWED");
        } catch (IOException ex) { put("jdk_readonly_open", ex.getClass().getSimpleName() + ":" + ex.getMessage()); }
        var interfaces = new ArrayList<String>();
        var enumeration = NetworkInterface.getNetworkInterfaces();
        while (enumeration != null && enumeration.hasMoreElements()) {
            var it = enumeration.nextElement(); interfaces.add(it.getName() + ":up=" + it.isUp() + ":loopback=" + it.isLoopback());
        }
        Collections.sort(interfaces); put("network_interfaces", String.join(",", interfaces));
        put("ipv4_routes", Files.readString(Path.of("/proc/net/route")).replace('\n','|'));
        put("ipv6_routes", Files.readString(Path.of("/proc/net/ipv6_route")).replace('\n','|'));
        put("parent_ipv4_connect", tcp("127.0.0.1", Integer.parseInt(args[0])));
        put("parent_ipv6_connect", tcp("::1", Integer.parseInt(args[1])));
        put("owned_ipv4_positive", loopbackPositive("127.0.0.1", Integer.parseInt(args[0]), Integer.parseInt(args[1])));
        put("owned_ipv6_positive", loopbackPositive("::1", Integer.parseInt(args[0]), Integer.parseInt(args[1])));
        Path unix = Path.of("/probe-output/owned-local.sock");
        try (ServerSocketChannel server = ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
            server.bind(UnixDomainSocketAddress.of(unix));
            try (SocketChannel client = SocketChannel.open(StandardProtocolFamily.UNIX)) {
                client.connect(UnixDomainSocketAddress.of(unix));
                try (SocketChannel accepted = server.accept()) {
                    client.write(java.nio.ByteBuffer.wrap(new byte[]{42}));
                    var one = java.nio.ByteBuffer.allocate(1); accepted.read(one);
                    put("owned_unix_positive", one.position() == 1 && one.array()[0] == 42);
                }
            }
        }
        var fds = new TreeMap<String,String>();
        try (var stream = Files.list(Path.of("/proc/self/fd"))) {
            for (Path fd : stream.toList()) {
                try { fds.put(fd.getFileName().toString(), Files.readSymbolicLink(fd).toString()); }
                catch (IOException ignored) { }
            }
        }
        put("fds_observed", fds);
        StringBuilder text = new StringBuilder();
        fields.forEach((key, value) -> text.append(key).append('=').append(value).append('\n'));
        Files.writeString(Path.of("/probe-output/result.txt"), text.toString(), StandardOpenOption.CREATE_NEW);
        System.out.print(text);
    }
}
