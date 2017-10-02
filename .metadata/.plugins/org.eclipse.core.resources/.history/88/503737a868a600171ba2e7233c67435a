/*
 * To change this template, choose Tools | Templates
 * and open the template in the editor.
 */
package nl.xupwup.Util;

import java.awt.image.BufferedImage;
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import javax.imageio.ImageIO;
import org.lwjgl.BufferUtils;
import static org.lwjgl.opengl.GL11.*;
/**
 *
 * @author rick
 */
public class Texture {
    
    int textureID;
    public final int width;
    public final int height;
    /**
     * 
     * @param image 
     */
    public Texture(BufferedImage image){
        width = image.getWidth();
        height = image.getHeight();
        int BYTES_PER_PIXEL = 4;
        int[] pixels = new int[image.getWidth() * image.getHeight()];
        image.getRGB(0, 0, image.getWidth(), image.getHeight(), pixels, 0, image.getWidth());

        ByteBuffer buffer = BufferUtils.createByteBuffer(image.getWidth() * image.getHeight() * BYTES_PER_PIXEL); //4 for RGBA, 3 for RGB
        
        for(int y = 0; y < image.getHeight(); y++){
            for(int x = 0; x < image.getWidth(); x++){
                int pixel = pixels[y * image.getWidth() + x];
                buffer.put((byte) ((pixel >> 16) & 0xFF));     // Red component
                buffer.put((byte) ((pixel >> 8) & 0xFF));      // Green component
                buffer.put((byte) (pixel & 0xFF));             // Blue component
                buffer.put((byte) ((pixel >> 24) & 0xFF));     // Alpha component. Only for RGBA
            }
        }

        buffer.flip(); //FOR THE LOVE OF GOD DO NOT FORGET THIS

        textureID = glGenTextures(); //Generate texture ID
        glBindTexture(GL_TEXTURE_2D, textureID); //Bind texture ID

        //Setup texture scaling filtering
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        
        glTexParameteri( GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT );
        glTexParameteri( GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT );
        
        // You now have a ByteBuffer filled with the color data of each pixel.
        // Now just create a texture ID and bind it. Then you can load it using 
        // whatever OpenGL method you want, for example:
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, image.getWidth(), image.getHeight(), 0, GL_RGBA, GL_UNSIGNED_BYTE, buffer);
        glBindTexture(GL_TEXTURE_2D, 0); //Bind texture ID
    }
    
    public void bind(){
        glBindTexture(GL_TEXTURE_2D, textureID); //Bind texture ID
    }
    
    public void unbind(){
        glBindTexture(GL_TEXTURE_2D, 0);
    }
    
    public void destroy(){
        glDeleteTextures(textureID);
    }
    
    public static Texture fromStream(InputStream s) throws IOException{
        BufferedImage i = ImageIO.read(s);
        return new Texture(i);
    }
    
    public void draw(float x, float y){
        bind();
        glBegin (GL_QUADS);
            glTexCoord2d(0, 0);
            glVertex3f (x, y, 0);
            glTexCoord2d(0, 1);
            glVertex3f (x, y + height, 0);
            glTexCoord2d(1, 1);
            glVertex3f (x + width, y + height, 0);
            glTexCoord2d(1, 0);
            glVertex3f (x + width, y, 0);
        glEnd ();
        unbind();
    }
}
