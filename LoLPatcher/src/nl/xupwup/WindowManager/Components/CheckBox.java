/*
 * To change this template, choose Tools | Templates
 * and open the template in the editor.
 */
package nl.xupwup.WindowManager.Components;

import nl.xupwup.WindowManager.Component;
import nl.xupwup.WindowManager.Listener;
import java.awt.Point;
import java.io.IOException;
import java.util.logging.Level;
import java.util.logging.Logger;
import nl.xupwup.Util.Texture;
import static org.lwjgl.opengl.GL11.*;

/**
 *
 * @author rick
 */
public class CheckBox extends Component{
    public boolean checked;
    public Listener call;
    int size = 20;
    private static Texture checkedtex = null;
    public static Texture uncheckedtex = null;
    
    public CheckBox(Listener c, Point location, boolean initial){
        call = c;
        this.location = location;
        checked = initial;
        if(checkedtex == null){
            try {
                checkedtex = Texture.fromStream(CheckBox.class.getResourceAsStream("/nl/xupwup/WindowManager/resources/checkboxC.png"));
                uncheckedtex = Texture.fromStream(CheckBox.class.getResourceAsStream("/nl/xupwup/WindowManager/resources/checkboxU.png"));
            } catch (IOException ex) {
                Logger.getLogger(CheckBox.class.getName()).log(Level.SEVERE, null, ex);
            }
        }
    }
    public CheckBox(Listener c, Point location){
        this(c, location, false);
    }

    @Override
    public Point getSize() {
        return new Point(size, size);
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

    @Override
    public void setLocation(Point location) {
        this.location = location;
    }
    
    

    @Override
    public void click(Point p) {
        checked = !checked;
        try {
            if(call != null) call.click(this);
        } catch (Exception ex) {
            ex.printStackTrace();
        }
    }

}
