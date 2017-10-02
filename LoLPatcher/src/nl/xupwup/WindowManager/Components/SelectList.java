/*
 * To change this template, choose Tools | Templates
 * and open the template in the editor.
 */

package nl.xupwup.WindowManager.Components;

import nl.xupwup.WindowManager.Component;
import nl.xupwup.WindowManager.Listener;
import java.awt.Point;
import java.util.ArrayList;
import static org.lwjgl.opengl.GL11.*;

/**
 *
 * @author Rick Hendricksen
 */
public class SelectList extends Component{
    ArrayList<Option> options;
    public int selected;
    Listener c;
    int h, w;
    int columns;
    
    public SelectList(String[] options, int columns, Listener c, Point location, int initial){
        this.options = new ArrayList<>();
        this.columns = columns;
        this.c = c;
        int padding = 3;
        int offset = 0;
        h = 0;
        w = 0;
        int tempw = 0;
        int wpad = 10;
        
        int colnr = 1;
        
        for(int i = 0; i < options.length; i++){
            if(i == colnr * (Math.ceil((float) options.length / columns))){
                w += tempw;
                h = Math.max(h, offset);
                offset = 0;
                colnr++;
            }
            String s = options[i];
            Option n = new Option(s, null, new Point(w != 0 ? wpad + w : w,offset), false, true);
            offset += n.getSize().y + padding;
            tempw = Math.max(tempw, n.getSize().x);
            this.options.add(n);
        }
        w += tempw;
        w += (colnr - 1) * wpad;
        h = Math.max(h, offset);
        h -= padding;
        select(selected = initial);
    }

    @Override
    public Point getSize() {
        return new Point(w, h);
    }

    @Override
    public void draw() {
        for(Option o : options){
            Point loc = o.getLocation();
            glPushMatrix();
            glTranslatef(loc.x, loc.y, 0);
            o.draw();
            glPopMatrix();
        }
    }

    @Override
    public void click(Point p) {
        for(int i = 0; i < options.size(); i++){
            Point loc = options.get(i).getLocation();
            Point dim = options.get(i).getSize();
            if(p.x > loc.x && p.x < loc.x + dim.x 
                    && p.y > loc.y && p.y < loc.y + dim.y){
                
                selected = i;
            }
        }
        select(selected);
        if(c != null) c.click(this);
    }
    
    private void select(int idx){
        for(int i = 0; i < options.size(); i++){
            options.get(i).cb.checked = i == idx;
        }
    }
}
