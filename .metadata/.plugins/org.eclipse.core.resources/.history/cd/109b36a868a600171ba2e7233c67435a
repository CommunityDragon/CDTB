package nl.xupwup.Util;

/**
 *
 * @author Rick
 */
public class Console {
    private static void log(String... strs){
        StackTraceElement e = Thread.currentThread().getStackTrace()[3];
        String s = e.getFileName() + ":" + e.getLineNumber() + "    ";
        System.out.print(s);
        for(String str : strs){
            System.out.println(str);
        }
    }
    public static final void log(Object... os){
        String[] strs = new String[os.length];
        for(int i = 0; i < os.length; i++){
            strs[i] = os[i].toString();
        }
        log(strs);
    }
}
