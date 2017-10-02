/*
 * To change this template, choose Tools | Templates
 * and open the template in the editor.
 */
package nl.xupwup.WindowManager;

import java.awt.Point;

/**
 *
 * @author rick
 */
public abstract class Component {
    public Point location;
    
    public Point getLocation(){
        return location;
    }
    
    public void setLocation(Point p){
        location = p;
    }
    
    public abstract Point getSize();
    
    public abstract void draw();
    
    public abstract void click(Point p);
    
    /**
     * 
     * @param p
     * @return false if dragging should stop
     */
    public boolean drag(Point p){
        return false;
    }
    
    public void release(){
        
    }
}
