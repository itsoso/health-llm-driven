// Source links verified 2026-10-27. Files remain at their publishers; no official-answer claim.
export const examPapers = [
  {
    "id": "2024-199",
    "year": 2024,
    "subject": "199",
    "url": "https://pdc.bit.edu.cn/docs/2025-09/871304dae4a245f8a70f32c540604faa.pdf",
    "source": "北京理工大学",
    "containsAnswers": true
  },
  {
    "id": "2024-204",
    "year": 2024,
    "subject": "204",
    "url": "https://pdc.bit.edu.cn/docs/2025-09/bbfa3fc39c39494c83c89c6bf0611e42.pdf",
    "source": "北京理工大学",
    "containsAnswers": true
  },
  {
    "id": "2025-199",
    "year": 2025,
    "subject": "199",
    "url": "https://pdc.bit.edu.cn/docs/2025-09/aa0b64304fd942d38bb5ea3cb7b243ae.pdf",
    "source": "北京理工大学",
    "containsAnswers": true
  },
  {
    "id": "2025-204",
    "year": 2025,
    "subject": "204",
    "url": "https://pdc.bit.edu.cn/docs/2025-09/cd4d2e557dab49a695bfe3d287069f36.pdf",
    "source": "北京理工大学",
    "containsAnswers": true
  },
  {
    "id": "2026-199",
    "year": 2026,
    "subject": "199",
    "url": "https://static.kaoyan.cn/file/question/2026/02/03/4099476555b47f9d67587eb6183c7de5.pdf",
    "source": "中国教育在线考研平台（第三方整理）",
    "containsAnswers": true
  },
  {
    "id": "2026-204",
    "year": 2026,
    "subject": "204",
    "url": "https://downloads.lazynote.cn/kaoyan/2026-english-two/%E8%80%83%E7%A0%94%E8%8B%B1%E8%AF%AD%E4%BA%8C2026%E5%B9%B4%E7%9C%9F%E9%A2%98%EF%BC%88%E6%95%B4%E5%8D%B7%EF%BC%89.pdf",
    "source": "懒笔记（第三方整理，待交叉核验）",
    "containsAnswers": false
  }
] as const;
const englishSections = ['阅读 Text 1，第21—25题','阅读 Text 2，第26—30题','阅读 Text 3，第31—35题','阅读 Text 4，第36—40题','完形填空，第1—20题','新题型，第41—45题','翻译，第46题','小作文，第47题','大作文，第48题'];
const comprehensiveSections = ['数学问题求解，第1—5题','数学问题求解，第6—10题','数学问题求解，第11—15题','条件充分性，第16—20题','条件充分性，第21—25题','逻辑，第26—35题','逻辑，第36—45题','逻辑，第46—55题','本轮错题复测；无错题时核对未完成题'];
export function paperAssignment(day: string) {
 if (!/^\d{4}-\d{2}-\d{2}$/.test(day) || day<'2026-10-27' || day>='2026-12-19') return null;
 const year=day<'2026-11-09'?2024:day<'2026-11-30'?2025:2026;
 const start=year===2024?'2026-10-27':year===2025?'2026-11-09':'2026-11-30';
 const offset=Math.floor((Date.parse(day+'T00:00:00Z')-Date.parse(start+'T00:00:00Z'))/86400000);
 const section=offset%9, review=offset>=9||day>='2026-12-14';
 return {year, review, round:Math.floor(offset/9)+1, english:englishSections[section], comprehensive:comprehensiveSections[section], writing:offset%2===0?'管综第56题：论证有效性分析；先列结论、前提、漏洞，再写一段':'管综第57题：论说文；先列论点、论据与反例，再写一段', papers:examPapers.filter(p=>p.year===year)};
}
