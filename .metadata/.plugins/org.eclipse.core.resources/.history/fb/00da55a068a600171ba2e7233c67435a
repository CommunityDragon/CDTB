/*
 * To change this template, choose Tools | Templates
 * and open the template in the editor.
 */
package nl.xupwup.WindowManager.Components;

import nl.xupwup.WindowManager.Component;
import nl.xupwup.Util.TextRenderHelper;
import java.awt.Point;
import nl.xupwup.Util.Color;
import static org.lwjgl.opengl.GL11.*;

/**
 *
 * @author rick
 */
public class Gradient extends Component{
    private final int width;
    private final static int height = 20;
    private final Color[] colors;
    private final float[] locations;
    private String leftLabel;
    private String rightLabel;
    private String middleLabel;
    
    private int middleLabelWidth;
    private int rightLabelWidth;
    
    
    /**
     * This is a gradient, with color stops and labels.
     * @param size  width of the gradient
     * @param colors  color of the color stops
     * @param locations  locations of the color stops
     * @param leftLabel  label for the left side (at 0%) (can be null)
     * @param rightLabel  label for the right side (at 100%) (can be null)
     */
    public Gradient(int size, Color[] colors, float[] locations, String leftLabel, String middleLabel, String rightLabel){
        if(colors.length != locations.length || colors.length < 2){
            throw new IllegalArgumentException("colors.length != locations.length || colors.length < 2");
        }
        if(locations[0] != 0 || locations[locations.length-1] != 1){
            throw new IllegalArgumentException("The first location MUST be 0 and the last MUST be 1");
        }
        this.width = size;
        this.colors = colors;
        this.locations = locations;
        String[] labels = new String[]{leftLabel, middleLabel, rightLabel};
        this.update(labels);
    }
    
    @Override
    public Point getSize() {
        int h = 0;
        if(leftLabel != null || rightLabel != null){
            h = TextRenderHelper.getHeight();
        }
        return new Point(width, height + h);
    }

    @Override
    public void draw() {
        glBegin(GL_QUAD_STRIP);
        for(int i = 0; i < locations.length; i++){
            colors[i].bind();
            glVertex2f(locations[i] * width, 0);
            glVertex2f(locations[i] * width, height);
        }
        glEnd();
        // border
        glColor3f(0.3f,0.3f,0.3f);
        glBegin(GL_LINE_STRIP);
            glVertex2f(0, 0);
            glVertex2f(width, 0);
            glVertex2f(width, height);
            glVertex2f(0, height);
        glEnd();
        if(leftLabel != null)
            TextRenderHelper.drawString(0, height, leftLabel);
        if(middleLabel != null)
            TextRenderHelper.drawString(width/2 - middleLabelWidth/2, height, middleLabel);
        if(rightLabel != null)
            TextRenderHelper.drawString(width - rightLabelWidth, height, rightLabel);
    }

    @Override
    public void click(Point p) {
        
    }
    
    public void update(String[] labels){
        this.leftLabel = labels[0];
        this.middleLabel = labels[1];
        this.rightLabel = labels[2];
        middleLabelWidth = middleLabel == null ? 0 : TextRenderHelper.getWidth(middleLabel);
        rightLabelWidth = rightLabel == null ? 0 : TextRenderHelper.getWidth(rightLabel);
    }
    
}
