/*
 * To change this template, choose Tools | Templates
 * and open the template in the editor.
 */
package nl.xupwup.Util;

/**
 *
 * @author rick
 */
public final class Vec2d {
    final public double x;
    final public double y;
    
    public Vec2d(double x, double y){
        this.x = x;
        this.y = y;
    }
    public Vec2d(double v){
        this.x = (this.y = v);
    }
    public Vec2d(){
        x = (y = 0);
    }
    
    public double length(){
        return Math.sqrt(x * x + y * y);
    }
    
    public Vec2d multiply(double f){
        return new Vec2d(x * f, y * f);
    }
    /**
     * component wise multiplication
     * @param v
     * @return 
     */
    public Vec2d multiply(Vec2d v){
        return new Vec2d(x * v.x, y * v.y);
    }
    
    public Vec2d div(double f){
        return new Vec2d(x / f, y / f);
    }
    /**
     * component wise division
     * @param v
     * @return 
     */
    public Vec2d div(Vec2d v){
        return new Vec2d(x / v.x, y / v.y);
    }
    
    public Vec2d add(Vec2d v){
        return new Vec2d(x + v.x, y + v.y);
    }
    public Vec2d add(double d){
        return new Vec2d(x + d, y + d);
    }
    
    public Vec2d minus(Vec2d v){
        return new Vec2d(x - v.x, y - v.y);
    }
    public Vec2d minus(double d){
        return new Vec2d(x - d, y - d);
    }
    public double dot(Vec2d v){
        return x * v.x + y * v.y;
    }
    
    public Vec2d normalized(){
        double l = length();
        if(l == 0){
            return new Vec2d();
        }else return div(l);
    }
    
    /**
     * Rotates the vector over angle rot in radians 
     */
    public Vec2d rotate(double rot){
        Vec2d result = new Vec2d(Math.cos(rot)*x-Math.sin(rot)*y, Math.sin(rot)*x+Math.cos(rot)*y);
        return result;
    }
    
    public boolean equals(Vec2d v){
        return v.x == x && v.y == y;
    }
    
    public double distSQ(Vec2d v){
        double xd = v.x - x;
        double yd = v.y - y;
        return xd * xd + yd * yd;
    }
    
    public Vec2d getPerpendicular(){
        return new Vec2d(-y, x);
    }
    
    /**
     * Projects this vector onto vector "on".
     * @param on
     * @return 
     */
    public Vec2d project(Vec2d on){
        return on.multiply(dot(on) / on.dot(on));
    }
    
    @Override
    public String toString(){
        return "(" + x + ", " + y + ")";
    }
}