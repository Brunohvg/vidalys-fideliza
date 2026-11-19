/* Máscara única de celular brasileiro, usada em todas as telas.
   Aceita digitar, colar com +55, com zero do DDD, com espaços ou traços. */

/** Só os dígitos do número nacional (DDD + número), sem +55 e sem zero inicial. */
export const phoneDigits=(raw:string)=>{
 let d=raw.replace(/\D/g,"");
 if(d.length>11&&d.startsWith("55"))d=d.slice(2);
 if(d.startsWith("0"))d=d.replace(/^0+/,"");
 return d;
};

/** (31) 98842-1170 para celular; (31) 3333-4444 para fixo. Formata enquanto digita, sem pular. */
export const formatPhone=(raw:string)=>{
 const all=phoneDigits(raw);
 const mobile=all.length>2&&all[2]==="9";
 const d=all.slice(0,mobile?11:10);
 if(!d)return "";
 if(d.length<=2)return "("+d;
 const head=mobile?5:4,ddd=d.slice(0,2),rest=d.slice(2);
 if(rest.length<=head)return `(${ddd}) ${rest}`;
 return `(${ddd}) ${rest.slice(0,head)}-${rest.slice(head)}`;
};

/** Número completo: celular com 11 dígitos (9 depois do DDD) ou fixo com 10. */
export const phoneComplete=(raw:string)=>{
 const d=phoneDigits(raw);
 return (d.length===11&&d[2]==="9")||(d.length===10&&d[2]!=="9"&&d[2]!=="0");
};
