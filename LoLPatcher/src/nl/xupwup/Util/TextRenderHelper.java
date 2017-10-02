/*
 * To change this template, choose Tools | Templates
 * and open the template in the editor.
 */

package nl.xupwup.Util;

import java.awt.Font;
import static org.lwjgl.opengl.GL11.*;

/**
 *
 * @author Rick Hendricksen
 */
public class TextRenderHelper {
    static TextRenderer ft = new TextRenderer(new Font("SansSerif", Font.PLAIN, 14), true);
    static TextRenderer ftB = new TextRenderer(new Font("SansSerif", Font.BOLD, 14), true);
    
    
    
    public static void drawString(int x, int y, String str){
        drawString(x, y, str, false);
    }
    
    public static void drawString(int x, int y, String str, boolean bold){
        drawString(x, y, str, Color.BLACK, bold);
    }
    public static void drawString(int x, int y, String str, Color c, boolean bold){
        glPushMatrix();
            glTranslatef(x, y, 0);
            glEnable(GL_TEXTURE_2D);
            c.bind();
            if(bold){
                ftB.draw(str);
            }else{
                ft.draw(str);
            }
            glDisable(GL_TEXTURE_2D);
        glPopMatrix();
    }
    
    public static int getWidth(String str){
        return getWidth(str, false);
    }
    public static int getWidth(String str, boolean bold){
        return (int) (bold ? ftB.getWidth(str) : ft.getWidth(str));
    }
    
    public static int getHeight(boolean bold){
        return bold ? ftB.getHeight() : ft.getHeight();
    }
    
    public static int getHeight(){
        return getHeight(false);
    }
}
