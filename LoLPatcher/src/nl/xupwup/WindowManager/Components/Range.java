/*
 * To change this template, choose Tools | Templates
 * and open the template in the editor.
 */

package nl.xupwup.WindowManager.Components;

import nl.xupwup.WindowManager.Component;
import nl.xupwup.WindowManager.Listener;
import java.awt.Point;
import static org.lwjgl.opengl.GL11.*;

/**
 *
 * @author Rick Hendricksen
 */
public class Range extends Component{
    final static int holdWaittime = 300;
    private final Button plus;
    private final Button min;
    public double value;
    private final TextField tf;
    private final Listener l;
    private final String text;
    private final Point size;
    private final int decimalPlaces;
    
    private Button dragButton = null;
    
    /**
     * $ will be replaced by the value
     * @param text  for example:  value: $
     * @param c  callback
     * @param location 
     */
    public Range(String text, Listener c, Point location, double initial, final double step){
        this.location = location;
        l = c;
        this.text = text;
        value = initial;
        String stepstr = step + "";
        stepstr = stepstr.replaceAll("0+$", "");
        
        int integerPlaces = stepstr.indexOf('.');
        
        decimalPlaces = stepstr.length() - integerPlaces - 1;
        
        min = new Button(" - ", new Listener() {
            @Override
            public void click(Component c) {
                value -= step;
                updateText();
            }
        }, new Point(0,0));
        plus = new Button("+", new Listener() {
            @Override
            public void click(Component c) {
                value += step;
                updateText();
            }
        }, new Point(min.getSize().x + 5,0));
        
        tf = new TextField(400, 150, "", new Point(plus.getLocation().x + plus.getSize().x + 5,0));
        size = new Point(0,0);
        updateText();
    }
    
    public final void updateText(){
        double v = Math.round(value * Math.pow(10, decimalPlaces)) / Math.pow(10, decimalPlaces);
        String t = "" + v;
        if(decimalPlaces == 0){
            t = t.replaceAll("\\.0+$", "");
        }
        tf.setText(text.replace("$", t));
        size.x = tf.getLocation().x + tf.getSize().x;
        
        size.y = Math.max(min.getSize().y, Math.max(plus.getSize().y, tf.getSize().y));
    }

    @Override
    public Point getSize() {
        return size;
    }

    @Override
    public void draw() { 
        glPushMatrix();
            glTranslatef(min.getLocation().x, min.getLocation().y, 0);
            min.draw();
        glPopMatrix();
        glPushMatrix();
            glTranslatef(plus.getLocation().x, plus.getLocation().y, 0);
            plus.draw();
        glPopMatrix();
        glPushMatrix();
            glTranslatef(tf.getLocation().x, tf.getLocation().y, 0);
            tf.draw();
        glPopMatrix();
    }

    @Override
    public void click(Point p) {
        if(p.x > min.getLocation().x && p.x < min.getLocation().x + min.getSize().x &&
                p.y > min.getLocation().y && p.y < min.getLocation().y + min.getSize().y){
            min.click(p);
            dragButton = min;
        }else if(p.x > plus.getLocation().x && p.x < plus.getLocation().x + plus.getSize().x &&
                p.y > plus.getLocation().y && p.y < plus.getLocation().y + plus.getSize().y){
            plus.click(p);
            dragButton = plus;
        }else{
            dragButton = null;
        }
        l.click(this);
    }

    @Override
    public boolean drag(Point p) {
        if(dragButton != null){
            if(p.x > dragButton.getLocation().x && p.x < dragButton.getLocation().x + dragButton.getSize().x &&
                    p.y > dragButton.getLocation().y && p.y < dragButton.getLocation().y + dragButton.getSize().y){
                
                if(System.currentTimeMillis() - holdWaittime > dragButton.clicktime){
                    dragButton.click(p);
                    dragButton.clicktime -= holdWaittime - holdWaittime / 4;
                    l.click(this);
                }
                dragButton.drag(p);
                return true;
            }else{
                return false;
            }
        }else{
            return false;
        }
    }

    @Override
    public void release() {
        if(dragButton != null){
            dragButton.release();
            dragButton = null;
        }
    }
    
}
