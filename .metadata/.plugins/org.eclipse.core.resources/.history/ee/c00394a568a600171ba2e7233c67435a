/*
 * To change this template, choose Tools | Templates
 * and open the template in the editor.
 */
package nl.xupwup.WindowManager;

import java.awt.Point;
import java.util.LinkedList;
import static org.lwjgl.opengl.GL11.*;

/**
 *
 * @author rick
 */
public class Panel {
    LinkedList<Component> contents;
    Point size;
    Component dragComponent = null;
    
    public Panel(){
        contents = new LinkedList<>();
        size = new Point(200, 200);
    }
    
    protected void addComponent(Component c){
        contents.add(c);
    }
    
    public void draw(){
        for(Component c : contents){
            glPushMatrix();
                glTranslatef(c.getLocation().x, c.getLocation().y, 0);
                c.draw();
            glPopMatrix();
        }
    }
    
    public void pack(){
        int x = 0;
        int y = 0;
        for(Component c : contents){
            x = Math.max(x, c.getLocation().x + c.getSize().x);
            y = Math.max(y, c.getLocation().y + c.getSize().y);
        }
        size.x = x;
        size.y = y;
    }
    
    /**
     * 
     * @param p
     * @return true if passed to contents
     */
    public boolean click(Point p){
        for(Component c : contents){
            if((p.x > c.getLocation().x && p.x < c.getLocation().x + c.getSize().x) && 
                    (p.y > c.getLocation().y && p.y < c.getLocation().y + c.getSize().y)){
                c.click(new Point(p.x - c.getLocation().x, p.y - c.getLocation().y));
                dragComponent = c;
                return true;
            }
        }
        release();
        return false;
    }
    
    public boolean drag(Point p){
        if(dragComponent != null){
            if((p.x > dragComponent.getLocation().x && p.x < dragComponent.getLocation().x + dragComponent.getSize().x) && 
                    (p.y > dragComponent.getLocation().y && p.y < dragComponent.getLocation().y + dragComponent.getSize().y)){
                
                return dragComponent.drag(new Point(p.x - dragComponent.getLocation().x, p.y - dragComponent.getLocation().y));
            }else{
                return false;
            }
        }else return false;
    }
    
    public void release(){
        if(dragComponent != null){
            dragComponent.release();
        }
        dragComponent = null;
    }
}
