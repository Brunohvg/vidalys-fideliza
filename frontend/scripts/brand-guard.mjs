import fs from "node:fs";
import path from "node:path";

const root=path.resolve(import.meta.dirname,"..");
const protectedFiles=[
 "src/MarketingHome.tsx",
 "src/marketing-home.css",
 "src/loyalty-dashboard.css",
 "src/ActionCenter.tsx",
 "public/brand-logo.svg",
 "public/brand-logo-white.svg",
 "public/brand-mark.svg",
 "public/favicon.svg"
];
const prohibited=[
 /#087f79\b/i, /#37d5bb\b/i, /#10253e\b/i, /#096b66\b/i,
 /#0b575a\b/i, /#0d4f52\b/i, /#114d50\b/i
];
const issues=[];
for(const rel of protectedFiles){
 const source=fs.readFileSync(path.join(root,rel),"utf8");
 for(const regex of prohibited){
  if(regex.test(source))issues.push(`${rel} contains legacy brand color ${regex.source}`);
 }
 if(rel.endsWith(".css")&&/!important/.test(source))
  issues.push(`${rel} uses !important; new UI must not rely on cascade patches`);
}
if(issues.length){
 console.error("Brand guard failed:\n"+issues.map(x=>"- "+x).join("\n"));
 process.exit(1);
}
console.log("Brand guard passed ("+protectedFiles.length+" files).");
