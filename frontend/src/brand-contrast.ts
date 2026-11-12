/** Contraste WCAG: o maior entre preto e branco tem >= 4.5:1
 * para cores sRGB válidas (incluindo tons intermediários).
 * Usado na prévia e na página pública para não divergir do que foi salvo.
 */
export function readableForeground(background:string):string {
  const hex=background.replace(/^#/,"");
  if(!/^[0-9a-f]{6}$/i.test(hex))return "#FFFFFF";
  const luminance=[0.2126,0.7152,0.0722].reduce((total,weight,index)=>{
    const value=parseInt(hex.slice(index*2,index*2+2),16)/255;
    const linear=value<=0.04045?value/12.92:((value+0.055)/1.055)**2.4;
    return total+weight*linear;
  },0);
  const white=1.05/(luminance+0.05);
  const black=(luminance+0.05)/0.05;
  return white>=black?"#FFFFFF":"#000000";
}
