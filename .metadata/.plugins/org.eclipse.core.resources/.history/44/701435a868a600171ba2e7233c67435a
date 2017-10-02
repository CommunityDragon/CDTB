package nl.xupwup.Util;

import org.lwjgl.opengl.GL11;

/**
 *
 * @author rick
 */
public class Color {
    public static final double GOLDEN_RATIO = 1.61803398875;
    public int r, g, b, a;
    
    public static final Color WHITE = new Color(255,255,255);
    public static final Color BLACK = new Color(0,0,0);
    public static final Color BLUE = new Color(66,82,255);
    public static final Color RED = new Color(255,56,56);
    public static final Color PURPLE = new Color(153, 43, 255);
    public static final Color YELLOW = new Color(255, 255, 0);
    
    
    public Color(float r, float g, float b){
        this((int) (r * 255), (int) (g * 255), (int) (b * 255));
    }
    
    public Color(float r, float g, float b, float a){
        this((int) (r * 255), (int) (g * 255), (int) (b * 255), (int)(a * 255));
    }
    
    public Color(int r, int g, int b){
        this(r, g, b, 255);
    }
    
    public Color(int r, int g, int b, int a){
        this.r = r;
        this.g = g;
        this.b = b;
        this.a = a;
    }
    
   /**
    * H runs from 0 to 360 degrees
    * S and V run from 0 to 100
    * 
    * http://www.cs.rit.edu/~ncs/color/t_convert.html
     * @param hh  hue
     * @param ss  saturation
     * @param vv  value
     * @return 
    */
    public static Color hsvToColor(float hh, int ss, int vv) {
        float r, g, b;

        float h = Math.max(0, Math.min(360, hh)) / 60f;
        float s = Math.max(0, Math.min(100, ss)) / 100f;
        float v = Math.max(0, Math.min(100, vv)) / 100f;

        int i = (int) Math.floor(h);
        float f = h - i; // factorial part of h
        float p = v * (1 - s);
        float q = v * (1 - s * f);
        float t = v * (1 - s * (1 - f));
        switch(i) {
            case 0: r = v; g = t; b = p; break;
            case 1: r = q; g = v; b = p; break;
            case 2: r = p; g = v; b = t; break;
            case 3: r = p; g = q; b = v; break;
            case 4: r = t; g = p; b = v; break;
            default:r = v; g = p; b = q;
        }
        return new Color(Math.round(r * 255), Math.round(g * 255), Math.round(b * 255));
    }

    @Override
    public String toString() {
        return "(" + r + ","+ g + "," + b + "," + a + ")";
    }
    
    public void bind(){
        GL11.glColor4f(r/255f, g/255f, b/255f, a/255f);
    }
    
}
