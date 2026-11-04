import java.nio.file.Files;
import java.nio.file.Path;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.Label;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

public final class Observe {
    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(Path.of(args[0]));
        new ClassReader(bytes).accept(new ClassVisitor(Opcodes.ASM9) {
            @Override public MethodVisitor visitMethod(int access, String name, String desc,
                    String signature, String[] exceptions) {
                if (!name.equals("applyControl") && !name.equals("captureControl")) return null;
                System.out.println("METHOD " + name + desc + " access=" + access);
                return new MethodVisitor(Opcodes.ASM9) {
                    int instruction;
                    @Override public void visitInsn(int opcode) {
                        System.out.println((instruction++) + " INSN opcode=" + opcode);
                    }
                    @Override public void visitIntInsn(int opcode, int operand) { instruction++; }
                    @Override public void visitVarInsn(int opcode, int slot) {
                        System.out.println((instruction++) + " VAR opcode=" + opcode + " slot=" + slot
                                + (opcode == Opcodes.ASTORE ? " ASTORE" : ""));
                    }
                    @Override public void visitTypeInsn(int opcode, String type) { instruction++; }
                    @Override public void visitFieldInsn(int opcode, String owner, String field, String d) { instruction++; }
                    @Override public void visitMethodInsn(int opcode, String owner, String method, String d, boolean itf) {
                        System.out.println((instruction++) + " INVOKE opcode=" + opcode + " " + owner + "." + method + d);
                    }
                    @Override public void visitInvokeDynamicInsn(String n,String d,org.objectweb.asm.Handle h,Object... a) { instruction++; }
                    @Override public void visitJumpInsn(int opcode, Label label) { instruction++; }
                    @Override public void visitLdcInsn(Object value) { instruction++; }
                    @Override public void visitIincInsn(int var, int increment) { instruction++; }
                    @Override public void visitTableSwitchInsn(int min,int max,Label d,Label... labels) { instruction++; }
                    @Override public void visitLookupSwitchInsn(Label d,int[] keys,Label[] labels) { instruction++; }
                    @Override public void visitMultiANewArrayInsn(String desc,int dims) { instruction++; }
                    @Override public void visitLocalVariable(String n,String d,String sig,Label s,Label e,int slot) {
                        System.out.println("LOCAL name=" + n + " desc=" + d + " slot=" + slot);
                    }
                    @Override public void visitMaxs(int stack,int locals) {
                        System.out.println("MAX stack=" + stack + " locals=" + locals + " instructions=" + instruction);
                    }
                };
            }
        }, 0);
    }
}
