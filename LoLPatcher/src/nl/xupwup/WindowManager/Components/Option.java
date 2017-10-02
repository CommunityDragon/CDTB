/*
 * To change this template, choose Tools | Templates
 * and open the template in the editor.
 */

package nl.xupwup.WindowManager.Components;

import nl.xupwup.WindowManager.Component;
import nl.xupwup.WindowManager.Listener;
import static org.lwjgl.opengl.GL11.*;
import java.awt.Point;

/**
 *
 * @author Rick Hendricksen
 */
public class Option extends Component{
    public CheckBox cb;
    private TextField tf;

    public Option(String str, Listener c, Point location, boolean initial, boolean radio){
        tf = new TextField(200, str, new Point(30, 0));
        if(radio){
            cb = new RadioBox(c, new Point(0, - 10 + tf.getSize().y/2), initial);
        }else{
            cb = new CheckBox(c, new Point(0, - 10 + tf.getSize().y/2), initial);
        }
        this.location = location;
    }
    
    public Option(String str, Listener c, Point location, boolean initial){
        this(str, c, location, initial, false);
    }
    
    public Option(String str, Listener c, Point location){
        this(str, c, location, false, false);
    }
    
    @Override
    public Point getSize() {
        return new Point(30 + tf.getSize().x, Math.max(tf.getSize().y, cb.getSize().y));
    }

    @Override
    public void draw() {
        glTranslatef(tf.getLocation().x, tf.getLocation().y, 0);
        tf.draw();
        glTranslatef(-tf.getLocation().x + cb.getLocation().x, cb.getLocation().y, 0);
        cb.draw();
    }

    @Override
    public void click(Point p) {
        cb.click(p);
    }
    
}
