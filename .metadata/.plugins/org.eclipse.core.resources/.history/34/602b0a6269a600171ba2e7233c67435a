/*
 * To change this template, choose Tools | Templates
 * and open the template in the editor.
 */
package nl.xupwup.WindowManager;

import nl.xupwup.Util.Color;
import nl.xupwup.Util.TextRenderHelper;
import nl.xupwup.Util.Texture;
import static org.lwjgl.opengl.GL11.*;

/**
 *
 * @author rick
 */
class TopControlsOption {
    
    boolean hide = false;
    public Listener l;
    public Texture t;
    public String name;
    static final Color textcol = new Color(0.3f, 0.3f, 0.3f);
    static final Color textcolhl = Color.BLACK;
    int namewidth;
    int nameheight;
    
    public TopControlsOption(String name, Texture t, Listener l){
        this.name = name;
        this.l = l;
        this.t = t;
        namewidth = TextRenderHelper.getWidth(name, true);
        nameheight = TextRenderHelper.getHeight(true);
    }
    
    public TopControlsOption(Texture t, Listener l){
        this.l = l;
        this.t = t;
        name = null;
    }
    
    public int getWidth(){
        int iw = (t == null ? 0 : TopControls.padding + t.width);
        return namewidth + iw; //padding
    }
    
    public TopControlsOption(String name, Listener l){
        this.name = name;
        this.l = l;
        this.t = null;
        namewidth = TextRenderHelper.getWidth(name, true);
        nameheight = TextRenderHelper.getHeight(true);
    }
    
    public void draw(boolean hl){
        int ih = (t == null ? nameheight : t.height);
        int iw = (t == null ? 0 : TopControls.padding + t.width);
        Color c = hl ? textcolhl : textcol;
        
        TextRenderHelper.drawString(iw, ih/2 - nameheight/2, name, c, true);
        if(t != null){
            glEnable(GL_TEXTURE_2D);
            c.bind();
            t.bind();
            glBegin(GL_QUADS);
                glTexCoord2f(0, 0);
                glVertex2d(0,0);
                glTexCoord2f(0, 1);
                glVertex2d(0, t.height);
                glTexCoord2f(1, 1);
                glVertex2d(t.width, t.height);
                glTexCoord2f(1, 0);
                glVertex2d(t.width, 0);
            glEnd();
            glDisable(GL_TEXTURE_2D);
        }
    }
}
