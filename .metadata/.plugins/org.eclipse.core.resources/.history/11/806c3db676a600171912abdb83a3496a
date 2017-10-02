/*
 * To change this template, choose Tools | Templates
 * and open the template in the editor.
 */

package nl.xupwup.WindowManager.Components;

import nl.xupwup.WindowManager.Listener;
import java.awt.Point;
import java.io.IOException;
import java.util.logging.Level;
import java.util.logging.Logger;
import nl.xupwup.Util.Texture;
import static org.lwjgl.opengl.GL11.*;

/**
 *
 * @author Rick Hendricksen
 */
public class RadioBox extends CheckBox{
    private static Texture checkedtex = null;
    private static Texture uncheckedtex = null;
    
    
    public RadioBox(Listener c, Point location, boolean initial){
        super(c, location, initial);
        if(checkedtex == null){
            try {
                checkedtex = Texture.fromStream(RadioBox.class.getResourceAsStream("/nl/xupwup/WindowManager/resources/radioC.png"));
                uncheckedtex = Texture.fromStream(RadioBox.class.getResourceAsStream("/nl/xupwup/WindowManager/resources/radioU.png"));
            } catch (IOException ex) {
                Logger.getLogger(CheckBox.class.getName()).log(Level.SEVERE, null, ex);
            }
        }
    }
    
    public RadioBox(Listener c, Point location){
        this(c, location, false);
    }
    
    @Override
    public void draw() {
        Point p = getSize();
        glColor3f(1,1,1);
        glEnable(GL_TEXTURE_2D);
        if(checked){
            checkedtex.bind();
        }else{
            uncheckedtex.bind();
        }
        glBegin(GL_QUADS);
            glTexCoord2f(0, 0);
            glVertex2f(0,0);
            glTexCoord2f(0, 1);
            glVertex2f(0,p.y);
            glTexCoord2f(1, 1);
            glVertex2f(p.x,p.y);
            glTexCoord2f(1, 0);
            glVertex2f(p.x,0);
        glEnd();
        glDisable(GL_TEXTURE_2D);
    }
}
