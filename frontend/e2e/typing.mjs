import puppeteer from "puppeteer-core";
const b = await puppeteer.launch({executablePath:"/usr/bin/google-chrome",args:["--no-sandbox"],headless:"new"});
const p = await b.newPage(); await p.setViewport({width:1360,height:860});
const errs=[]; p.on("pageerror",e=>errs.push(String(e)));
const w=ms=>new Promise(r=>setTimeout(r,ms));
await p.goto("http://127.0.0.1:8765/",{waitUntil:"networkidle0"});
const go=t=>p.evaluate(t=>[...document.querySelectorAll("nav button")].find(b=>b.title===t).click(),t);
async function typeTest(label, sel, idx=0){
  const els=await p.$$(sel); const el=els[idx]; await el.click({clickCount:3}); await p.keyboard.press("Backspace");
  const s="Hei dette er en lang test 123"; let lost=0;
  for(const ch of s){ await p.keyboard.type(ch); const ok=await p.evaluate((sel,idx)=>document.activeElement===document.querySelectorAll(sel)[idx],sel,idx); if(!ok) lost++; }
  const v=await p.evaluate((sel,idx)=>document.querySelectorAll(sel)[idx].value,sel,idx);
  console.log(label,"lost focus:",lost,"value ok:",v===s);
}
await go("Settings"); await w(800);
await typeTest("agent-navn","input.w-full",0);
await typeTest("bruker-navn","input.w-full",1);
await typeTest("persona","textarea",0);
const y0=await p.evaluate(()=>document.querySelector(".overflow-auto").scrollTop);
await p.screenshot({path:"/downloads/nexus/ui-settings-typing.png"});
await go("Memory"); await w(600); await typeTest("memory","input[maxlength='500']",0);
await go("Assistant"); await w(600); await typeTest("assistant","textarea",0);
await go("Agents"); await w(600);
await p.evaluate(()=>[...document.querySelectorAll("button")].find(b=>b.textContent.includes("Lag eksempel")).click()); await w(1000);
await typeTest("rom-chat","textarea",0);
console.log("errors",errs); await b.close();
