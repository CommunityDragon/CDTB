/*
 * To change this template, choose Tools | Templates
 * and open the template in the editor.
 */
package nl.xupwup.WindowManager;


import nl.xupwup.Util.TextRenderHelper;
import nl.xupwup.Util.FrameBuffer;
import nl.xupwup.Util.ShaderProgram;
import java.awt.Point;
import java.io.IOException;
import java.util.logging.Level;
import java.util.logging.Logger;
import nl.xupwup.Util.Color;
import nl.xupwup.Util.GLFramework;
import org.lwjgl.opengl.Display;
import static org.lwjgl.opengl.GL11.*;
import static org.lwjgl.opengl.GL20.*;

/**
 *
 * @author rick
 */
public class Window {
    String title;
    protected Panel panel;
    public Point location;
    float opacity = 1;
    float active;
    int titlewidth;
    
    public boolean canClose = true;
    int borderTopSize = 25;
    int borderSize = 3;
    
    Color activeWindowHighlight = new Color(0, 166, 255);
    Color activeWindow = new Color(88, 194, 255);
    Color inactiveWindowHightlight = new Color(61, 161, 235);
    Color inactiveWindow = new Color(61, 161, 207);
    
    private static ShaderProgram shadowShader = null;
    private static ShaderProgram blurShader = null;
    
    public Window(Point loc, String title){
        panel = new Panel();
        this.title = title;
        location = loc;
        titlewidth = TextRenderHelper.getWidth(title, true);
    }
    
    public Point getSize(){
        return new Point(Math.max(panel.size.x + 2*borderSize, titlewidth + 2*borderSize + 34), panel.size.y + borderSize + borderTopSize);
    }
    
    public void pack(){
        panel.pack();
    }
    
    /**
     * Adds component c to this window.
     * If c.location == null, the component will be automatically positioned.
     * @param c 
     */
    public void addComponent(Component c){
        if(c.location == null){
            Point p = new Point(0,0);
            if(panel.contents.size() > 0){
                Component last = panel.contents.peekLast();
                p.y = last.getLocation().y + last.getSize().y+5;
            }
            c.setLocation(p);
        }
        panel.addComponent(c);
        panel.pack();
    }
    
    /**
     * 
     * @param p
     * @return true if passed to contents, false if clicked on border
     */
    public boolean click(Point p){
        if((p.y > borderTopSize && p.y < getSize().y - borderSize) && (p.x > borderSize && p.x < getSize().x - borderSize)){
            panel.click(new Point(p.x - borderSize, p.y - borderTopSize));
            return true;
        }else return false;
    }
    
    /**
     * 
     * @param p
     * @return if the point p is still in this window
     */
    public boolean drag(Point p){
        if((p.y > borderTopSize && p.y < getSize().y - borderSize) && (p.x > borderSize && p.x < getSize().x - borderSize)){
            return panel.drag(new Point(p.x - borderSize, p.y - borderTopSize));
        }else return false;
    }
    
    public void release(){
        panel.release();
    }
    
    private void shaderInit() throws IOException{
        shadowShader = ShaderProgram.getFromStream(ClassLoader.class.getResourceAsStream("/nl/xupwup/WindowManager/resources/shadow.frag"), 
                                                    ClassLoader.class.getResourceAsStream("/nl/xupwup/WindowManager/resources/shadow.vert"));
        blurShader = ShaderProgram.getFromStream(ClassLoader.class.getResourceAsStream("/nl/xupwup/WindowManager/resources/blur.frag"), 
                                                 ClassLoader.class.getResourceAsStream("/nl/xupwup/WindowManager/resources/blur.vert"));
    }
    
    public void draw(boolean act, boolean drag, FrameBuffer backBuffer){
        if(shadowShader == null){
            try {
                shaderInit();
            } catch (IOException ex) {
                Logger.getLogger(Window.class.getName()).log(Level.SEVERE, null, ex);
            }
        }
        
        
        float newopacity = (drag ? 0.7f : 1);
        opacity = (6 * opacity + newopacity) / 7;
        active = (6 * active + (act ? 1 : 0)) / 7;
        
        glColor4f(0,0,0, 0.4f);
        drawShadow();
        
        if(GLFramework.useBlur){
            blurShader.enable();
            glEnable(GL_TEXTURE_2D);
            glUniform1i(blurShader.getUniformLocation("winx"), Display.getWidth());
            glUniform1i(blurShader.getUniformLocation("winy"), Display.getHeight());
            glUniform1i(blurShader.getUniformLocation("topbarh"), TopControls.height);
            glBindTexture(GL_TEXTURE_2D, backBuffer.framebuffertex);
        }
        glBegin(GL_TRIANGLE_FAN);
            glColor3f(active * activeWindowHighlight.r/255f + (1-active) * inactiveWindowHightlight.r/255f,
                      active * activeWindowHighlight.g/255f + (1-active) * inactiveWindowHightlight.g/255f,
                      active * activeWindowHighlight.b/255f + (1-active) * inactiveWindowHightlight.b/255f);
            glVertex2f(getSize().x / 2f,0);
            glColor3f(active * activeWindow.r/255f + (1-active) * inactiveWindow.r/255f,
                      active * activeWindow.g/255f + (1-active) * inactiveWindow.g/255f,
                      active * activeWindow.b/255f + (1-active) * inactiveWindow.b/255f);
            glVertex2f(0, 0);
            glVertex2f(0, getSize().y);
            glVertex2f(getSize().x, getSize().y);
            glVertex2f(getSize().x, 0);
        glEnd();
        if(GLFramework.useBlur){
            glBindTexture(GL_TEXTURE_2D, 0);
            glDisable(GL_TEXTURE_2D);
            blurShader.disable();
        }
        
        
        glColor4f(0,0,0, 0.3f);
        glBegin(GL_LINE_STRIP);
            glVertex2f(0, 0);
            glVertex2f(0, getSize().y);
            glVertex2f(getSize().x, getSize().y);
            glVertex2f(getSize().x, 0);
            glVertex2f(0, 0);
        glEnd();
        
        int width = TextRenderHelper.getWidth(title, true);
        int xoff = (getSize().x - width) / 2;
        
        TextRenderHelper.drawString(xoff, 3, title, new Color(0,0,0, opacity), true);
        
        if(canClose) TextRenderHelper.drawString(getSize().x - 17, 2, "×", true);
        glTranslatef(borderSize, borderTopSize, 0);
        panel.draw();
    }
    
    
    private void drawShadow(){
        float pad = 20;
        
        shadowShader.enable();
        glBegin(GL_QUADS);
            // top left corner
            glTexCoord2f(1, 1);
            glVertex2f(-pad, -pad);
            glTexCoord2f(1, 0);
            glVertex2f(-pad, 0);
            glTexCoord2f(0, 0);
            glVertex2f(0, 0);
            glTexCoord2f(0, 1);
            glVertex2f(0, -pad);
            
            // left bar
            glTexCoord2f(1, 0);
            glVertex2f(-pad, 0);
            glTexCoord2f(1, 0);
            glVertex2f(-pad, getSize().y);
            glTexCoord2f(0, 0);
            glVertex2f(0, getSize().y);
            glTexCoord2f(0, 0);
            glVertex2f(0, 0);
            
            // bottom left corner
            glTexCoord2f(1, 0);
            glVertex2f(-pad, getSize().y); 
            glTexCoord2f(1, 1);
            glVertex2f(-pad, getSize().y + pad);
            glTexCoord2f(0, 1);
            glVertex2f(0, getSize().y + pad);
            glTexCoord2f(0, 0);
            glVertex2f(0, getSize().y);
            
            // top right corner
            glTexCoord2f(0, 1);
            glVertex2f(getSize().x, -pad); 
            glTexCoord2f(0, 0);
            glVertex2f(getSize().x, 0);
            glTexCoord2f(1, 0);
            glVertex2f(getSize().x + pad, 0);
            glTexCoord2f(1, 1);
            glVertex2f(getSize().x + pad, -pad);
            
            // right bar
            glTexCoord2f(0, 0);
            glVertex2f(getSize().x, 0);
            glTexCoord2f(0, 0);
            glVertex2f(getSize().x, getSize().y);
            glTexCoord2f(1, 0);
            glVertex2f(getSize().x + pad, getSize().y);
            glTexCoord2f(1, 0);
            glVertex2f(getSize().x + pad, 0);
            
            // bottom right corner
            glTexCoord2f(0, 0);
            glVertex2f(getSize().x, getSize().y);
            glTexCoord2f(0, 1);
            glVertex2f(getSize().x, getSize().y + pad);
            glTexCoord2f(1, 1);
            glVertex2f(getSize().x + pad, getSize().y + pad);
            glTexCoord2f(1, 0);
            glVertex2f(getSize().x + pad, getSize().y);
            
            // top bar
            glTexCoord2f(0, 1);
            glVertex2f(0, -pad);
            glTexCoord2f(0, 0);
            glVertex2f(0, 0);
            glTexCoord2f(0, 0);
            glVertex2f(getSize().x, 0);
            glTexCoord2f(0, 1);
            glVertex2f(getSize().x, -pad);
            
            // bottom bar
            glTexCoord2f(0, 0);
            glVertex2f(0, getSize().y);
            glTexCoord2f(0, 1);
            glVertex2f(0, getSize().y + pad);
            glTexCoord2f(0, 1);
            glVertex2f(getSize().x, getSize().y + pad);
            glTexCoord2f(0, 0);
            glVertex2f(getSize().x, getSize().y);
        glEnd();
        shadowShader.disable();
    }
}
