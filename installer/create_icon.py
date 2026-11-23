"""Create a friendly pencil-holding baby mascot for Windows installer shortcuts."""
from pathlib import Path
from PIL import Image, ImageDraw
import math

N=512
S=4
im=Image.new("RGBA",(N*S,N*S),(0,0,0,0))
d=ImageDraw.Draw(im)
def p(*v): return tuple(int(x*S) for x in v)
def ellipse(box,fill,outline=None,width=1):
    d.ellipse(p(*box),fill=fill,outline=outline,width=width*S)
def rounded(box,radius,fill,outline=None,width=1):
    d.rounded_rectangle(p(*box),radius=radius*S,fill=fill,outline=outline,width=width*S)
def polygon(pts,fill,outline=None,width=1):
    pts=[p(*pt) for pt in pts]
    d.polygon(pts,fill=fill)
    if outline:d.line(pts+[pts[0]],fill=outline,width=width*S,joint="curve")
# Blue backdrop makes the illustration visible as a small app shortcut.
rounded((22,22,490,490),106,"#CBEFFD","#3D9DCC",8)
ellipse((60,62,455,455),"#E7F9FF")
# Soft blue outfit
ellipse((125,308,389,474),"#7AC6F1","#286F9B",6)
ellipse((115,380,206,470),"#FED9BE","#8F5543",5)
ellipse((293,380,390,470),"#FED9BE","#8F5543",5)
ellipse((170,310,342,465),"#F9FEFF","#3A86B6",7)
ellipse((200,323,313,405),"#90D8FA","#3A86B6",4)
# ears and face
ellipse((94,193,163,279),"#FFCFB4","#875040",5)
ellipse((351,193,422,279),"#FFCFB4","#875040",5)
ellipse((115,110,401,353),"#FFDDC5","#875040",8)
ellipse((170,147,216,196),"#A85630")
ellipse((213,115,299,168),"#98502C")
ellipse((259,122,324,172),"#98502C")
# eyes, cheeks and mouth
ellipse((174,213,214,264),"#2D2928")
ellipse((302,213,342,264),"#2D2928")
ellipse((184,221,198,236),"white")
ellipse((312,221,326,236),"white")
ellipse((148,267,201,296),"#F5A7A6")
ellipse((316,267,367,296),"#F5A7A6")
ellipse((244,261,267,276),"#E6A086")
ellipse((222,290,297,329),"#9E3B47")
ellipse((237,309,282,330),"#EF8C97")
# pencil behind raised hand, placed diagonally
# shaft oriented toward upper-right
polygon([(349,252),(378,265),(474,93),(446,75)],"#FFCB30","#9B5D17",6)
polygon([(446,75),(474,93),(469,39)],"#F8DDAD","#9B5D17",5)
polygon([(469,39),(455,61),(473,63)],"#3E3B3B")
polygon([(349,252),(378,265),(366,285),(336,273)],"#F48D9F","#9B5D17",4)
ellipse((335,251,397,316),"#FFD4B5","#875040",5)
# little curls and shine
ellipse((237,97,295,135),"#8F4A2A")
ellipse((253,77,300,114),"#8F4A2A")
# output regular PNG and multi-resolution .ico
im=im.resize((N,N),Image.Resampling.LANCZOS)
dest=Path(__file__).resolve().parent
im.save(dest/"siaaebi_icon.png")
im.save(dest/"siaaebi_icon.ico",format="ICO",sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
print("Created installer/siaaebi_icon.ico")
