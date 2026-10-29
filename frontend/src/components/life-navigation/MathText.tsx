import React from 'react';
import katex from 'katex';
import css from './server-exam-practice.module.css';

const mathPattern = /(\$\$[\s\S]+?\$\$|\$(?:\\.|[^$\\])+?\$)/g;

export default function MathText({children}:{children:string}) {
 const parts=children.split(mathPattern);
 return <span className={css.mathText}>{parts.map((part,index)=>{
  const display=part.startsWith('$$')&&part.endsWith('$$');
  const inline=!display&&part.startsWith('$')&&part.endsWith('$');
  if(!display&&!inline)return <React.Fragment key={index}>{part}</React.Fragment>;
  const source=part.slice(display?2:1,display?-2:-1);
  try {
   const html=katex.renderToString(source,{displayMode:display,throwOnError:true,strict:'warn',trust:false,output:'htmlAndMathml'});
   return <span key={index} className={css.math} dangerouslySetInnerHTML={{__html:html}}/>;
  } catch {
   return <React.Fragment key={index}>{part}</React.Fragment>;
  }
 })}</span>;
}
