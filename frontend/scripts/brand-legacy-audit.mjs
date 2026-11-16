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
 "#00d1e6":"ciano antigo"
};
const results=[];
for(const filename of fs.readdirSync(directory).filter(file=>file.endsWith(".css"))){
 const content=fs.readFileSync(path.join(directory,filename),"utf8").toLowerCase();
 const hits=Object.entries(legacy).flatMap(([color,description])=>{
  const count=content.split(color).length-1;
  return count>0?[{color,count,description}]:[];
 });
 if(hits.length)results.push({file:filename,total:hits.reduce((n,x)=>n+x.count,0),hits});
}
results.sort((a,b)=>b.total-a.total);
console.log("Auditoria de cores antigas (somente inventário; não representa cores renderizadas):");
if(!results.length)console.log("Nenhuma ocorrência dos tons antigos monitorados.");
for(const item of results){
 console.log(`- ${item.file}: ${item.total} ocorrências — ${item.hits.map(x=>x.color+" ("+x.count+")").join(", ")}`);
}
console.log("Total: "+results.reduce((n,x)=>n+x.total,0)+" ocorrências em "+results.length+" arquivos.");
