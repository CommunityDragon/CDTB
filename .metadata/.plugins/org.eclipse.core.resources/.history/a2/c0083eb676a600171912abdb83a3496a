/*
 * To change this template, choose Tools | Templates
 * and open the template in the editor.
 */
package nl.xupwup.WindowManager.Components;

import nl.xupwup.WindowManager.Component;
import nl.xupwup.WindowManager.Listener;
import java.awt.Point;
import java.io.IOException;
import nl.xupwup.Util.Color;
import nl.xupwup.Util.Texture;
import static org.lwjgl.opengl.GL11.*;

/**
 *
 * @author rick
 */
public class Slider extends Component{

    float colanim = 0;
    long clicktime = 0;
    final static int highlighttime = 300;
    Listener call;
    Color standardColor = new Color(236, 236, 236);
    Color activeColor = new Color(210, 245, 138);
    int height = 15;
    int width;
    static Texture slider;
    Point clickOffset = null;
    int handleWidth = 5;
    public float value = 0;
    
    public Slider(int width, Listener c, float initial, Point l){
        call = c;
        this.location = l;
        this.width = width;
        value = initial;
        if(CheckBox.uncheckedtex == null){
            try {
                CheckBox.uncheckedtex = Texture.fromStream(Button.class.getResourceAsStream("/nl/xupwup/WindowManager/resources/checkboxU.png"));
            } catch (IOException ex) {
                ex.printStackTrace();
            }
        }
        if(slider == null){
            try {
                slider = Texture.fromStream(Slider.class.getResourceAsStream("/nl/xupwup/WindowManager/resources/slider.png"));
            } catch (IOException ex) {
                ex.printStackTrace();
            }
        }
    }
    
    @Override
    public Point getSize() {
        return new Point(width, height);
    }

    @Override
    public void draw() {
        if(System.currentTimeMillis() - highlighttime > clicktime){
            colanim = (3 * colanim + 0) / 4;
        }else{
            colanim = (2 * colanim + 1) / 3;
        }
        glEnable(GL_TEXTURE_2D);
        
        slider.bind();
        glColor3f(1,1,1);
        glBegin(GL_QUAD_STRIP);
            glTexCoord2f(0, 0);
            glVertex2f(0, -2 + height / 2);
            glTexCoord2f(0, 1);
            glVertex2f(0,2 + height / 2);
            
            glTexCoord2f(0.2f, 0);
            glVertex2f(handleWidth,-2 + height / 2);
            glTexCoord2f(0.2f, 1);
            glVertex2f(handleWidth,2 + height / 2);
            
            glTexCoord2f(0.8f, 0);
            glVertex2f(width - handleWidth,-2 + height / 2);
            glTexCoord2f(0.8f, 1);
            glVertex2f(width - handleWidth,2 + height / 2);
            
            glTexCoord2f(1, 0);
            glVertex2f(width,-2 + height / 2);
            glTexCoord2f(1, 1);
            glVertex2f(width,2 + height / 2);
        glEnd();
        CheckBox.uncheckedtex.bind();
        glColor3f(activeColor.r * colanim/255f + standardColor.r * (1-colanim)/255f,
                  activeColor.g * colanim/255f + standardColor.g * (1-colanim)/255f, 
                  activeColor.b * colanim/255f + standardColor.b * (1-colanim)/255f);
        
        
        glBegin(GL_QUAD_STRIP);
            glTexCoord2f(0, 0);
            glVertex2f((width- 2 * handleWidth) * value,0);
            glTexCoord2f(0, 1);
            glVertex2f((width- 2 * handleWidth) * value,height);
            
            glTexCoord2f(0.3f, 0);
            glVertex2f((width- 2 * handleWidth) * value + 3,0);
            glTexCoord2f(0.3f, 1);
            glVertex2f((width- 2 * handleWidth) * value + 3,height);
            
            glTexCoord2f(0.7f, 0);
            glVertex2f((width- 2 * handleWidth) * value + (2 * handleWidth - 3),0);
            glTexCoord2f(0.7f, 1);
            glVertex2f((width- 2 * handleWidth) * value + (2 * handleWidth - 3),height);
            
            glTexCoord2f(1, 0);
            glVertex2f((width- 2 * handleWidth) * value + 2 * handleWidth,0);
            glTexCoord2f(1, 1);
            glVertex2f((width- 2 * handleWidth) * value + 2 * handleWidth,height);
        glEnd();
        glDisable(GL_TEXTURE_2D);

    }

    @Override
    public void click(Point p) {
        if(p.x >= width * value - handleWidth && p.x <= width * value + handleWidth &&
           p.y >= 0 && p.y <= height){
            
            clickOffset = new Point((int) (p.x - (width * value)), p.y);
        }else{
            value = Math.max(0, (float) p.x / width);
            try {
                if(call != null) call.click(this);
            } catch (Exception ex) {
                ex.printStackTrace();
            }
        }
        clicktime = System.currentTimeMillis();
    }

    @Override
    public boolean drag(Point p) {
        if(clickOffset != null){
            value = Math.max(0, (float) (p.x - clickOffset.x) / width);
        }else{
            value = Math.max(0, (float) p.x / width);
        }
        try {
            if(call != null) call.click(this);
        } catch (Exception ex) {
            ex.printStackTrace();
        }
        return true;
    }

    @Override
    public void release() {
        clickOffset = null;
    }
}
