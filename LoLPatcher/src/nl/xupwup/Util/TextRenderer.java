package nl.xupwup.Util;

import java.awt.Font;
import java.awt.FontMetrics;
import java.awt.Graphics;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.awt.image.WritableRaster;
import java.nio.FloatBuffer;
import org.lwjgl.BufferUtils;
import static org.lwjgl.opengl.GL11.*;

/**
 *
 * @author Rick Hendricksen
 */
public class TextRenderer {
    private static final int vpad = 2;
    private static final int hpad = 1;

    private double[] charwidths;
    private double[] charcoordx;
    private double[] charcoordy;
    
    private Texture tex;
    
    private int dimx;
    private int dimy;
    
    private int charheight;
    
    char[][] ranges = new char[][]{
        new char[]{32, 126},  // 32 = space (HEX 20), 126 = tilde, 127 = delete character ( left out)
        new char[]{161, 383}, // 161 = inverted exclamation mark, 383 = last character in LATIN EXTENDED-A
        new char[]{9703, 9703}// ◧
    };
    
    
    public TextRenderer(Font font, boolean antialias){
        this(font, antialias, null);
    }
    
    /**
     * 
     * @param font
     * @param antialias  Standard smoothing, not subpixel rendering.
     * @param extraRanges array like: [[rStart, rEnd], [rStart2, rEnd2]] where rStart denotes the start of a character range, and rEnd the end.
     *                    Note that both rStart and rEnd are inclusive, so one-character ranges are created when rStart = rEnd
     */
    public TextRenderer(Font font, boolean antialias, char[][] extraRanges){
        if(extraRanges != null && extraRanges.length > 0){
            for(char[] range : extraRanges){
                if(range.length != 2){
                    throw new IllegalArgumentException("Invalid argument for extraranges.");
                }
            }
            char[][] newranges = new char[ranges.length + extraRanges.length][];
            System.arraycopy(ranges, 0, newranges, 0, ranges.length);
            System.arraycopy(extraRanges, 0, newranges, ranges.length, extraRanges.length);
            ranges = newranges;
        }
        
        int count = 0;
        for(char[] range : ranges){
            count += 1 + range[1] - range[0];
        }
        charwidths = new double[count];
        charcoordx = new double[count];
        charcoordy = new double[count];
        
        
        getCharWidths(font);
        
        
        double surface = 0;
        for(double d : charwidths){
            surface += d + hpad;
        }
        surface *= charheight+vpad; // +padding
        surface *= 1.1; // protect against too small texture (suboptimal rounding)
        
        dimx = (int) Math.ceil(Math.sqrt(surface));
        if(Integer.highestOneBit(dimx) != dimx) {
            dimx = Integer.highestOneBit(dimx) << 1;
        }
        
        dimy = (int) Math.ceil(surface / dimx);
        if(Integer.highestOneBit(dimy) != dimy){
            dimy = Integer.highestOneBit(dimy) << 1;
        }

        BufferedImage b = new BufferedImage(dimx, dimy, BufferedImage.TYPE_4BYTE_ABGR);
        wipeImage(b);
        
        Graphics2D g2d = (Graphics2D) b.getGraphics();
        FontMetrics fm = g2d.getFontMetrics();
        g2d.setColor(java.awt.Color.WHITE);
        g2d.setFont(font);
        if(antialias){
            g2d.setRenderingHint(
                RenderingHints.KEY_TEXT_ANTIALIASING,
                RenderingHints.VALUE_TEXT_ANTIALIAS_ON);
        }else{
            g2d.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING,
                RenderingHints.VALUE_TEXT_ANTIALIAS_GASP);
        }
        
        writeCharacterPage(g2d, fm);
        
        tex = new Texture(b);
        /*try {
            ImageIO.write(b, "png", new File("aap.png"));
        } catch (IOException ex) {
            Logger.getLogger(TextRenderer.class.getName()).log(Level.SEVERE, null, ex);
        }*/
    }
    
    
    public void draw(String s){
        draw(s, 0,0);
    }
    
    /**
     * Draw a string.
     * The top left corner of the first character is at 0,0.
     * @pre GL_TEXTURE_2D is enabled
     * @param s (newlines are allowed)
     * 
     * coordinates of the rendered quads are in pixels
     */
    public void draw(String s, float x, float y){
        FloatBuffer texcoords = BufferUtils.createFloatBuffer(s.length() * 4 * 2); // 4 2d floats per letter
        FloatBuffer coords = BufferUtils.createFloatBuffer(s.length() * 4 * 2); // 4 2d floats per letter
        
        float xcoord = x;
        float ycoord = y;
        int nnewlines = 0;
        
        for(int i = 0; i < s.length(); i++){
            if(s.charAt(i) == '\n'){
                ycoord += charheight;
                xcoord = x;
                nnewlines ++;
                continue;
            }
            int idx = getIndexOfChar(s.charAt(i));
            float charx = (float) charcoordx[idx] / dimx;
            float chary = (float) charcoordy[idx] / dimy;
            float w =     (float) charwidths[idx];
            
            texcoords.put(charx           ).put(chary);
            texcoords.put(charx           ).put(chary + (float) charheight / dimy);
            texcoords.put(charx + w / dimx).put(chary + (float) charheight / dimy);
            texcoords.put(charx + w / dimx).put(chary);
            
            coords.put(xcoord    ).put(ycoord);
            coords.put(xcoord    ).put(ycoord + charheight);
            coords.put(xcoord + w).put(ycoord + charheight);
            coords.put(xcoord + w).put(ycoord);
            
            xcoord += charwidths[idx];
        }
        texcoords.flip();
        coords.flip();
        
        
        tex.bind();
        glEnableClientState(GL_VERTEX_ARRAY);
        glVertexPointer(2, 0, coords);
        glEnableClientState(GL_TEXTURE_COORD_ARRAY);
        glTexCoordPointer(2, 0, texcoords);
        
        glDrawArrays(GL_QUADS, 0, 4 * (s.length() - nnewlines));
        
        glDisableClientState(GL_VERTEX_ARRAY);
        glDisableClientState(GL_TEXTURE_COORD_ARRAY);
        tex.unbind();
    }
    
    public float getWidth(String s){
        float w = 0;
        for(int i = 0; i < s.length(); i++){
            w += charwidths[getIndexOfChar(s.charAt(i))];
        }
        return w;
    }
    /**
     * 
     * @return The height of a character.
     */
    public int getHeight(){
        return charheight;
    }
    
    /**
     * You can use getHeight() if your string does not contain newlines. (faster)
     * @param s
     * @return The height of a string. Takes newlines into account.
     */
    public int getHeight(String s){
        int y = 0;
        for(int i = 0; i < s.length(); i++){
            if(s.charAt(i) == '\n'){
                y += charheight;
            }
        }
        return y + charheight;
    }
    
    
    private int getIndexOfChar(int c){
        int count = 0;
        for(char[] range : ranges){
            if(c >= range[0] && c <= range[1]){
                return count + (c - range[0]);
            }
            count += 1 + range[1] - range[0];
        }
        return getIndexOfChar(9703); // fallback
    }
    
    
    private void getCharWidths(Font font){
        BufferedImage b = new BufferedImage(50, 50, BufferedImage.TYPE_INT_ARGB); // needed to get graphics object
        Graphics g = b.getGraphics();
        g.setFont(font);

        
        FontMetrics fm = g.getFontMetrics();
        
        for(char[] range : ranges){
            for(char i = range[0]; i <= range[1]; i++){
                String str = new String(new char[]{i});
                charwidths[getIndexOfChar(i)] = fm.getStringBounds(str, g).getWidth();
            }
        }
        
        charheight = fm.getHeight();
    }
    
    private void wipeImage(BufferedImage b){
        WritableRaster r = b.getRaster();
        for(int i = 0; i < r.getWidth(); i ++){
            for(int j = 0; j < r.getHeight(); j++){
                r.setPixel(i, j, new int[]{0,0,0,0});
            }
        }
        b.setData(r);
    }
    
    private void writeCharacterPage(Graphics2D g2d, FontMetrics fm){
        double x = 0;
        double y = 0;
        
        for(char[] range : ranges){
            for(char i = range[0]; i <= range[1]; i++){
                int idx = getIndexOfChar(i);
                double w = charwidths[idx];
                if(x + w > dimx){
                    x = 0;
                    y += charheight+vpad;
                }

                charcoordx[idx] = x;
                charcoordy[idx] = y;

                String str = new String(new char[]{i});
                g2d.drawString(str, (int) x, (int) (fm.getHeight() + y - fm.getDescent()));


                x += w + hpad;
            }
        }
    }
    
    public static String wordWrap(String towrap, TextRenderer tr, float width){
        String[] lines = towrap.split("\n");
        StringBuilder sb2 = new StringBuilder();
        
        for(String line : lines){
            StringBuffer sb = new StringBuffer();
            String[] words = line.split(" ");
            
            for(String word : words){
                if(sb.length() != 0){
                    sb.append(" ");
                    sb.append(word);
                    if(tr.getWidth(sb.toString()) > width){
                        sb.delete(sb.length() - word.length() - 1, sb.length());
                        if(sb2.length() > 0){
                            sb2.append("\n");
                        }
                        sb2.append(sb.toString());
                        sb = new StringBuffer();
                        sb.append(word);
                    }
                }else{
                    sb.append(word);
                }
            }
            if(sb2.length() > 0 && sb.length() > 0){
                sb2.append("\n");
                sb2.append(sb);
            }
        }
        return sb2.toString();
    }
    public static String trim(String toTrim, TextRenderer tr, int width){
        StringBuilder sb = new StringBuilder();
        int w = 0;
        for(int i = 0; i < toTrim.length(); i++){
            if(tr.getWidth(sb.toString() + toTrim.charAt(i)) <= width){
                sb.append(toTrim.charAt(i));
            }else{
                return trim2(sb, tr, width);
            }
        }
        return toTrim;
    }
    private static String trim2(StringBuilder toTrim, TextRenderer tr, int width){
        while(tr.getWidth(toTrim.toString() + "...") > width){
            if(toTrim.length() == 0){
                return "";
            }
            toTrim.deleteCharAt(toTrim.length() - 1);
        }
        return toTrim.toString() + "...";
    }
}
