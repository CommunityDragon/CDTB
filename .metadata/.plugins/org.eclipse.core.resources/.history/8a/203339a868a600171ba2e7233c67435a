package nl.xupwup.Util;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import org.lwjgl.opengl.GL11;

import static org.lwjgl.opengl.GL20.*;

/**
 *
 * @author Rick Hendricksen
 */
public class ShaderProgram {
    public int program = 0;
    public int vertShader, fragShader;
            
    
    private static void debuggle(){
        int err = GL11.glGetError();
        if(err != 0){
            try{
                throw new Exception("error: " + err);
            }catch(Exception e){
                e.printStackTrace();
            }
        }
    }
    
    /**
     * Load a shader. If you only need a vertex shader, leave the argument for 'frag' empty. (empty string) The same holds the other way around.
     * @param vert  The vertex shader
     * @param frag  The fragment shader
     */
    public ShaderProgram(String vert, String frag){
        vertShader = vert.equals("") ? 0 : genShader(vert, true);
        fragShader = frag.equals("") ? 0 : genShader(frag, false);
        program = glCreateProgram();
        if(vertShader == 0 && fragShader == 0){
            glDeleteProgram(program);
            program = 0;
            System.err.println("Not creating shader object.");
            return;
        }
        if(vertShader != 0) glAttachShader(program, vertShader);
        if(fragShader != 0) glAttachShader(program, fragShader);
        glLinkProgram(program);

        String log = glGetProgramInfoLog(program, 2000);
        if (glGetProgrami(program, GL_LINK_STATUS) == GL11.GL_FALSE) {
            System.err.println(log);
        }
    }
    
    
    public int getUniformLocation(String name){
        int loc = glGetUniformLocation(program, name);
        if(loc == -1){
            System.err.println("Uniform " + name + " not found.");
        }
        return loc;
    }
    
    public static int genShader(String code, boolean type){
        int vertShader = glCreateShader(type ? GL_VERTEX_SHADER : GL_FRAGMENT_SHADER);
        if(vertShader == 0){
            System.err.println("Shader creation failed.");
            return 0;
        }
        glShaderSource(vertShader, code);
        glCompileShader(vertShader);
        
        String log = glGetShaderInfoLog(vertShader, 2000);
        if (glGetShaderi(vertShader, GL_COMPILE_STATUS) == GL11.GL_FALSE) {
            System.err.println(log);
            vertShader = 0;
        }
        return vertShader;
    }
    
    public void enable(){
        glUseProgram(program);
    }
    public void disable(){
        glUseProgram(0);
    }
    
    public static ShaderProgram getFromStream(InputStream fragStream, InputStream vertStream) throws IOException{
        StringBuilder frag = new StringBuilder();
        try(BufferedReader r = new BufferedReader(
                new InputStreamReader(fragStream))){
            
            String s;
            while((s = r.readLine()) != null){
                frag.append(s).append("\n");
            }
        }
        StringBuilder vert = new StringBuilder();
        try(BufferedReader r = new BufferedReader(
                new InputStreamReader(vertStream))){
            
            String s;
            while((s = r.readLine()) != null){
                vert.append(s).append("\n");
            }
        }
        return new ShaderProgram(vert.toString(), frag.toString());
    }
}
