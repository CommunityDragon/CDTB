/*
 * To change this template, choose Tools | Templates
 * and open the template in the editor.
 */
package nl.xupwup.Util;

import java.nio.ByteBuffer;
import static org.lwjgl.opengl.GL30.*;
import static org.lwjgl.opengl.GL20.glDrawBuffers;
import static org.lwjgl.opengl.GL11.*;

/**
 *
 * @author rick
 */
public class FrameBuffer {
    
    public int framebuffertex;
    int framebuffer;
    
    int xsize;
    int ysize;
    int textureType;
    
    
    public FrameBuffer(int xsize, int ysize){
        this(xsize, ysize, GL_TEXTURE_2D, GL_RGBA8, GL_RGBA);
    }
    public FrameBuffer(int xsize, int ysize, int textureType, int type1, int type2){
        this.xsize = xsize;
        this.ysize = ysize;
        framebuffer = glGenFramebuffers();
        framebuffertex = glGenTextures();
        
        glBindFramebuffer(GL_FRAMEBUFFER, framebuffer);
        glBindTexture(textureType, framebuffertex);
        glTexImage2D(textureType, 0, type1, xsize, ysize, 0, type2, GL_FLOAT, (ByteBuffer) null);
        
        glTexParameteri(textureType, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
        glTexParameteri(textureType, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
        
        
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, textureType, framebuffertex, 0);
        
        glDrawBuffers(GL_COLOR_ATTACHMENT0);
        
        glViewport(0, 0, xsize, ysize);
        glBindFramebuffer(GL_FRAMEBUFFER, 0);
    }
    
    public void drawBuffer(){
        glEnable(GL_TEXTURE_2D);
        glBindTexture(GL_TEXTURE_2D, framebuffertex);
        glMatrixMode (GL_MODELVIEW);
        glPushMatrix ();
        glLoadIdentity ();
        glMatrixMode (GL_PROJECTION);
        glPushMatrix ();
        glLoadIdentity ();
        glBegin (GL_QUADS);
            glTexCoord2d(0, 0);
            glVertex3i (-1, -1, -1);
            glTexCoord2d(1, 0);
            glVertex3i (1, -1, -1);
            glTexCoord2d(1, 1);
            glVertex3i (1, 1, -1);
            glTexCoord2d(0, 1);
            glVertex3i (-1, 1, -1);
        glEnd ();
        glPopMatrix ();
        glMatrixMode (GL_MODELVIEW);
        glBindTexture(GL_TEXTURE_2D, 0);
        glPopMatrix ();
        
    }
    
    public void bind(){
        glBindFramebuffer(GL_FRAMEBUFFER, framebuffer);
        glViewport(0, 0, xsize, ysize);
    }
    
    public void unbind(){
        glBindFramebuffer(GL_FRAMEBUFFER, 0);
    }
    
    public void destroy(){
        glDeleteFramebuffers(framebuffer);
        glDeleteTextures(framebuffertex);
    }
    
}
