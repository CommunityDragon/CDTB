/*
 * To change this template, choose Tools | Templates
 * and open the template in the editor.
 */
package nl.xupwup.WindowManager.Components;

import nl.xupwup.WindowManager.Component;
import nl.xupwup.Util.TextRenderHelper;
import java.awt.Point;
import java.util.LinkedList;
import nl.xupwup.Util.Color;

/**
 *
 * @author rick
 */
public class TextField extends Component{

    private String text;
    public int width;
    public int maxwidth;
    public int minwidth;
    private static int charHeight = TextRenderHelper.getHeight();
    private int height;
    
    public TextField(int width, String text, Point location){
        this(width, 0, text, location);
    }
    public TextField(int width, Point location){
        this(width, "", location);
    }
    
    public TextField(int width, int minwidth, String text, Point location){
        this.minwidth = minwidth;
        this.width = width;
        maxwidth = width;
        setText(text);
        this.location = location;
    }
    
    public final void setText(String text){
        width = maxwidth;
        String[] a = text.split("\n");
        LinkedList<String> temp = new LinkedList<>();
        
        for(String s : a){
            temp.add("");
            int w = 0;
            String[] b = s.split(" ");
            
            for(String ss : b){
                int wordwidth = TextRenderHelper.getWidth((w == 0 ? "" : " ") + ss);
                if(w + wordwidth > width){
                    w = wordwidth;
                    temp.add(ss);
                }else{
                    temp.add(temp.removeLast() + (w == 0 ? "" : " ") + ss);
                    w += wordwidth;
                }
            }
        }
        int maxw = 0;
        StringBuilder sb = new StringBuilder();
        boolean first = true;
        for(String s : temp){
            int w = TextRenderHelper.getWidth(s);
            if(w > maxw){
                maxw = w;
            }
            if(!first){
                sb.append('\n');
            }
            first = false;
            sb.append(s);
        }
        this.text = sb.toString();
        width = Math.max(maxw, minwidth);
        height = temp.size() * charHeight;
    }

    @Override
    public Point getSize() {
        return new Point(width, height);
    }

    @Override
    public void draw() {
        TextRenderHelper.drawString(0, 0, text, Color.BLACK, false);
    }

    @Override
    public void click(Point p) {
        // do nothing
    }
    
}
