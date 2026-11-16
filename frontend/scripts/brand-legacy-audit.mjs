import fs from "node:fs";
import path from "node:path";

const directory=path.resolve(import.meta.dirname,"../src");
const legacy={
 "#087f79":"jade principal antigo",
 "#37d5bb":"menta antiga",
 "#10253e":"azul-marinho antigo",
 "#096b66":"verde antigo",
 "#0b575a":"verde-petróleo antigo",
 "#0d4f52":"verde-petróleo antigo",
 "#114d50":"verde-petróleo antigo",
 "#12806e":"verde antigo",
 "#0a7d6b":"verde antigo",
 "#0b806c":"verde antigo",
 "#00bbd1":"ciano antigo",
 "#00d1e6":"ciano antigo",
 "#081b29":"fundo de login antigo",
 "#123b45":"gradiente petróleo antigo",
 "#0c5b57":"gradiente verde antigo",
 "#66e7c7":"destaque menta antigo",
 "#6de5c4":"ícone menta antigo"
};
const legacyRgb = [
 {name:"jade RGB",regex:/rgba?\\(\\s*8\\s*,\\s*127\\s*,\\s*121\\s*(?:,|\\))/gi},
 {name:"menta RGB",regex:/rgba?\\(\\s*55\\s*,\\s*213\\s*,\\s*187\\s*(?:,|\\))/gi},
 {name:"marinho RGB",regex:/rgba?\\(\\s*16\\s*,\\s*37\\s*,\\s*62\\s*(?:,|\\))/gi}
];
const results=[];
for(const filename of fs.readdirSync(directory).filter(file=>file.endsWith(".css"))){
 const content=fs.readFileSync(path.join(directory,filename),"utf8").toLowerCase();
 const hits=Object.entries(legacy).flatMap(([color,description])=>{
  const count=content.split(color).length-1;
  return count>0?[{color,count,description}]:[];
 });
 for(const {name,regex} of legacyRgb){
  const count=(content.match(regex)||[]).length;
  if(count)hits.push({color:name,count,description:"efeito com RGB da marca anterior"});
 }
 if(hits.length)results.push({file:filename,total:hits.reduce((n,x)=>n+x.count,0),hits});
}
results.sort((a,b)=>b.total-a.total);
console.log("Auditoria de cores antigas (somente inventário; não representa cores renderizadas):");
if(!results.length)console.log("Nenhuma ocorrência dos tons antigos monitorados.");
for(const item of results){
 console.log(`- ${item.file}: ${item.total} ocorrências — ${item.hits.map(x=>x.color+" ("+x.count+")").join(", ")}`);
}
console.log("Total: "+results.reduce((n,x)=>n+x.total,0)+" ocorrências em "+results.length+" arquivos.");

const approved=new Set([
 "#f8f9ff","#ede7ff","#e4dff2","#3b1e82","#6a3df0","#ffc857",
 "#ff8a3d","#f3eeff","#ffffff","#f8f6ff","#24113f","#513595",
 "#f0e9ff","#167a56"
]);
function obsoleteHue(hex){
 const rgb=[1,3,5].map(n=>parseInt(hex.slice(n,n+2),16)/255);
 const maximum=Math.max(...rgb),minimum=Math.min(...rgb),difference=maximum-minimum;
 if(difference===0)return false;
 let hue=maximum===rgb[0]?(rgb[1]-rgb[2])/difference%6:
         maximum===rgb[1]?(rgb[2]-rgb[0])/difference+2:(rgb[0]-rgb[1])/difference+4;
 hue=(hue*60+360)%360;
 const lightness=(maximum+minimum)/2;
 const saturation=difference/(1-Math.abs(2*lightness-1))||0;
 return hue>=95&&hue<=250&&saturation>.095;
}
const semantic=/\\b(success|paid|approved|confirmed|refund|cancelled|canceled|error|danger|warning|negative|positive|green|invalid|failed|verified|healthy|ready|settled)\\b/i;
const residual=[];
for(const filename of fs.readdirSync(directory).filter(name=>name.endsWith(".css"))){
 const source=fs.readFileSync(path.join(directory,filename),"utf8");
 for(const found of source.matchAll(/#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?\\b/g)){
  const hex=found[0].slice(0,7).toLowerCase();
  if(approved.has(hex)||!obsoleteHue(hex))continue;
  const rule=source.slice(source.lastIndexOf("}",found.index)+1,source.lastIndexOf("{",found.index));
  if(semantic.test(rule))continue;
  residual.push({filename,hex,rule:rule.trim().replace(/\\s+/g," ").slice(-80)});
 }
}
console.log("Tons azuis/verdes residuais fora de estados semânticos: "+residual.length);
for(const entry of residual.slice(0,25))console.log("  "+entry.filename+" "+entry.hex+" "+entry.rule);
if(residual.length>25)console.log("  ...e mais "+(residual.length-25)+" ocorrências");
