/*
 * To change this template, choose Tools | Templates
 * and open the template in the editor.
 */
package nl.xupwup.WindowManager;

import java.awt.image.BufferedImage;
import java.util.ArrayList;
import nl.xupwup.Util.Color;
import nl.xupwup.Util.Texture;
import static org.lwjgl.opengl.GL11.*;

/**
 *
 * @author rick
 */
public class TopControls {
    static final int padding = 2;
    public static int height = 20;
    ArrayList<TopControlsOption> controls;
    static final Color highlight = new Color(58, 128, 232);
    
    public TopControls(){
        controls = new ArrayList<>();
    }
    
    public void addOption(BufferedImage icon, String text, Listener l){
        Texture t = new Texture(icon);
        controls.add(new TopControlsOption(text, t, l));
    }
    public void addOption(BufferedImage icon, Listener l){
        Texture t = new Texture(icon);
        controls.add(new TopControlsOption(t, l));
    }
    public void addOption(String text, Listener l){
        controls.add(new TopControlsOption(text, l));
    }
    /**
     * Hides or unhides an option. (flips hide bit)
     * @param text
     * @return whether or not the option is now hidden (true if not found)
     */
    public boolean hideOption(String text){
        for(TopControlsOption t : controls){
            if(t.name.equals(text)){
                t.hide = !t.hide;
                return t.hide;
            }
        }
        return true;
    }
    
    /**
     * Hides or unhides an option.
     * @param text
     * @param newvalue  true=hidden, false=visible
     * @return whether or not the new value was applied
     */
    public boolean hideOption(String text, boolean newvalue){
        for(TopControlsOption t : controls){
            if(t.name.equals(text)){
                t.hide = newvalue;
                return true;
            }
        }
        return false;
    }
    
    
    public void click(int x){
        TopControlsOption o = getAtX(x);
        if(o != null && o.l != null){
            o.l.click(null);
        }
    }
        
    private TopControlsOption getAtX(int x){
        int xi = TopControls.padding;
        for(TopControlsOption o : controls){
            if(o.hide) continue;
            if(x > xi && x < xi + o.getWidth()){
                return o;
            }
            xi += o.getWidth() + 2 * TopControls.padding;
        }
        return null;
    }
    
    public void draw(int w, int mousex){
        glMatrixMode(GL_PROJECTION);
        glLoadIdentity();
        glOrtho(0, w, height, 0, 0, 1.0f);
        glMatrixMode(GL_MODELVIEW);
        glLoadIdentity();
        glDisable(GL_TEXTURE_2D);
        glColor3f(0.8f, 0.8f, 0.8f);
        glBegin(GL_QUADS);
            glVertex2d(0, 0);
            glVertex2d(0, height);
            glVertex2d(w, height);
            glVertex2d(w, 0);
        glEnd();
        
        int x = 2;
        for(TopControlsOption o : controls){
            if(o.hide) continue;
            glPushMatrix();
                glTranslatef(x, 2, 0);
                boolean hl = mousex > x && mousex < x + o.getWidth();
                o.draw(hl);
                if(hl){
                    highlight.bind();
                    glBegin(GL_QUADS);
                        glVertex2d(0, height - 4);
                        glVertex2d(0, height - 2);
                        glVertex2d(o.getWidth(), height-2);
                        glVertex2d(o.getWidth(), height - 4);
                    glEnd();
                }
                x += o.getWidth() + 2 * TopControls.padding;
            glPopMatrix();
        }
    }
}
