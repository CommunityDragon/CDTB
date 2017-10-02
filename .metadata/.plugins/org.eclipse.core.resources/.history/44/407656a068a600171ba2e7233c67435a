/*
 * To change this template, choose Tools | Templates
 * and open the template in the editor.
 */
package nl.xupwup.WindowManager.Components;

import nl.xupwup.WindowManager.Component;
import nl.xupwup.WindowManager.Listener;
import nl.xupwup.Util.TextRenderHelper;
import java.awt.Point;
import java.io.IOException;
import nl.xupwup.Util.Color;
import nl.xupwup.Util.Texture;
import static org.lwjgl.opengl.GL11.*;


/**
 *
 * @author rick
 */
public class Button extends Component{
    
    float colanim = 0;
    long clicktime = 0;
    final static int highlighttime = 300;
    Listener call;
    String text;
    int padding = 4;
    Color standardColor = new Color(236, 236, 236);
    Color activeColor = new Color(210, 245, 138);
    
    /**
     * 
     * @param text  the button's label
     * @param c  A function to call on click
     * @param location  this object's position inside the window
     */
    public Button(String text, Listener c, Point location){
        call = c;
        this.text = text;
        
        this.location = location;
        
        if(CheckBox.uncheckedtex == null){
            try {
                CheckBox.uncheckedtex = Texture.fromStream(Button.class.getResourceAsStream("/nl/xupwup/WindowManager/resources/checkboxU.png"));
            } catch (IOException ex) {
                ex.printStackTrace();
            }
        }
    }
    
    @Override
    public Point getSize() {
        int h = TextRenderHelper.getHeight();
        int w = TextRenderHelper.getWidth(text);
        return new Point(w + 2*padding, h+2*padding);
    }

    @Override
    public void draw() {
        if(System.currentTimeMillis() - highlighttime > clicktime){
            colanim = (3 * colanim + 0) / 4;
        }else{
            colanim = (2 * colanim + 1) / 3;
        }
        
        glColor3f(activeColor.r * colanim / 255f + standardColor.r * (1-colanim) / 255f,
                  activeColor.g * colanim / 255f + standardColor.g * (1-colanim) / 255f, 
                  activeColor.b * colanim / 255f + standardColor.b * (1-colanim) / 255f);
        glEnable(GL_TEXTURE_2D);
        CheckBox.uncheckedtex.bind();
        Point p = getSize();
        glBegin(GL_QUAD_STRIP);
            glTexCoord2f(0, 0);
            glVertex2f(0,0);
            glTexCoord2f(0, 1);
            glVertex2f(0,p.y);
            
            glTexCoord2f(0.2f, 0);
            glVertex2f(3,0);
            glTexCoord2f(0.2f, 1);
            glVertex2f(3,p.y);
            
            glTexCoord2f(0.8f, 0);
            glVertex2f(p.x - 3,0);
            glTexCoord2f(0.8f, 1);
            glVertex2f(p.x - 3,p.y);
            
            glTexCoord2f(1, 0);
            glVertex2f(p.x,0);
            glTexCoord2f(1, 1);
            glVertex2f(p.x,p.y);
        glEnd();
        TextRenderHelper.drawString(3, p.y / 2 - TextRenderHelper.getHeight()/2, text);
    }

    @Override
    public void click(Point p) {
        try {
            if(call != null) call.click(this);
        } catch (Exception ex) {
            ex.printStackTrace();
        }
        clicktime = System.currentTimeMillis();
    }  
}
