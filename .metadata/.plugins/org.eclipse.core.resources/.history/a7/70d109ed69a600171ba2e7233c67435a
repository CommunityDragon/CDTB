package nl.xupwup.WindowManager;

import nl.xupwup.Util.FrameBuffer;
import java.awt.Point;
import java.util.LinkedList;
import nl.xupwup.Util.GLFramework;
import static org.lwjgl.opengl.GL11.*;

/**
 *
 * @author rick
 */
public class WindowManager {
    LinkedList<Window> windows;
    Window dragged = null;
    Window contentDrag = null;
    Point clickInWinPoint;
    long dragStart = -1;
    
    public WindowManager(){
        windows = new LinkedList<>();
    }
    
    public void draw(FrameBuffer front, FrameBuffer back){
        init2d((int) GLFramework.windowSize.x, (int) GLFramework.windowSize.y);
        for(int i = 0; i < windows.size(); i++){
            Window w = windows.get(i);
            if(front != null){
                front.bind();
                glClearColor(0,0,0,0);
                glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
            }
            glPushMatrix();
                glTranslatef(w.location.x,w.location.y,0);
                w.draw(i == windows.size()-1, w == dragged && dragStart < System.currentTimeMillis() - 200, back);
            glPopMatrix();
            if(back != null) back.bind();
            glColor4f(1,1,1, w.opacity);
            if(front != null) front.drawBuffer();
        }
        leave2d();
    }
    
    /**
     * Add window w to the stack, at the top. If this window is already in the
     * stack it will be raised.
     * @param w 
     */
    public void addWindow(Window w){
        if(!windows.contains(w)){
            windows.add(w);
        }else{
            raise(w);
        }
    }
    
    /**
     * 
     * @param w
     * @return true if window w has focus, false if w is not open, or doesn't have focus
     */
    public boolean hasFocus(Window w){
        if(!windows.contains(w)){
            return false;
        }else{
            return windows.size() > 0 && windows.get(windows.size()-1) == w;
        }
    }
    
    public void closeWindow(Window w){
        windows.remove(w);
    }
    
    public void closeAllWindows(){
        windows.clear();
    }
    
    /**
     * Raise a window to the top of the stack.
     * @param w 
     */
    public void raise(Window w){
        if(windows.peekLast() != w){
            windows.remove(w);
            windows.add(w);
        }
    }
    
    /**
     * Try to click a window.
     * @param x
     * @param y
     * @return Whether a window was clicked
     */
    public boolean click(int x, int y){
        for(int i = windows.size()-1; i >=0; i--){
            Window w = windows.get(i);
            if((x < w.location.x + w.getSize().x && x > w.location.x) &&
               (y < w.location.y + w.getSize().y && y > w.location.y)){
                
                raise(w);
                clickInWinPoint = new Point(x - w.location.x, y - w.location.y);
                if(!w.click(clickInWinPoint)){
                    if((clickInWinPoint.x < w.getSize().x - 5 && clickInWinPoint.x > w.getSize().x - 20) &&
                            (clickInWinPoint.y < 20 && clickInWinPoint.y > 5) && w.canClose){
                        windows.remove(w);
                    }else {
                        dragged = w;
                        dragStart = System.currentTimeMillis();
                    }
                }else{
                    contentDrag = w;
                }
                return true;
            }
        }
        release();
        return false;
    }
    
    public boolean hitTest(int x, int y){
        for(int i = windows.size()-1; i >=0; i--){
            Window w = windows.get(i);
            if((x < w.location.x + w.getSize().x && x > w.location.x) &&
               (y < w.location.y + w.getSize().y && y > w.location.y)){

                return true;
            }
        }
        return false;
    }
    
    /**
     * Call this when the mouse is being dragged.
     * @param x
     * @param y 
     */
    public void drag(int x, int y){
        if(dragged != null) {
            dragged.location.x = x - clickInWinPoint.x;
            dragged.location.y = y - clickInWinPoint.y;
        }else if(contentDrag != null){
            clickInWinPoint = new Point(x - contentDrag.location.x, y - contentDrag.location.y);
            if(!contentDrag.drag(clickInWinPoint)){
                release();
            }
        }
    }
    
    /**
     * Call this when the mouse is released.
     */
    public void release(){
        dragged = null;
        if(contentDrag != null){
            contentDrag.release();
        }
        contentDrag = null;
    }
    
    
    /**
     * Sets up the display for 2d drawing. Do not forget calling leave2d after finishing your 2d drawing.
     * @param w  window width
     * @param h  window height
     * @param gl
     */
    private void init2d(int w, int h) {
        glMatrixMode(GL_PROJECTION);
        glPushMatrix();
        glLoadIdentity();
        glOrtho(0, w, h, 0, 0, 1.0f);
        glMatrixMode(GL_MODELVIEW);
        glPushMatrix();
        glLoadIdentity();
        
        glLineWidth(1);
        glPushAttrib(GL_DEPTH_TEST);
        glPushAttrib(GL_TEXTURE_2D);
        glPushAttrib(GL_LIGHTING);
        glDisable(GL_DEPTH_TEST);
        glDisable(GL_LIGHTING);
        glDisable(GL_TEXTURE_2D);
    }
    
    /**
     * Sets up display for 3d drawing
     * @pre init2d() has been called before this.
     * @param gl
     */
    private void leave2d() {
        glPopAttrib(); // LIGHTING
        glPopAttrib(); // TEXTURE_2D
        glPopAttrib(); // DEPTH_TEST
        glMatrixMode(GL_PROJECTION);
        glPopMatrix();
        glMatrixMode(GL_MODELVIEW);
        glPopMatrix();
    }
}
