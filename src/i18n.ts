// Interface language. The language setting controls (1) every functional label in the UI and (2) the language
// PaperLens answers in. "PaperLens" and paper titles are never translated. Values that are stored or logged
// (verdicts, reading goals) stay in English; only their display is translated, so evaluation data stays comparable.
import { createContext, useContext } from 'react';
import type { SectionKind, Source, Verdict } from './api';

export const LANGUAGES = ['English', '中文（简体）', '中文（繁體）', '日本語'] as const;
export type Language = (typeof LANGUAGES)[number];
export const isLanguage = (value: unknown): value is Language => LANGUAGES.includes(value as Language);

// Canonical reading goals (stored on the session and sent to the model).
export const GOAL_OVERVIEW = 'Get a general overview of this paper';
export const GOAL_REPRODUCE = 'Reproduce the study or method';
export const GOAL_RESEARCH = 'Explore potential use in my research';
export const GOAL_OTHER = 'Other (described by the learner in chat)';
export const GOALS = [GOAL_OVERVIEW, GOAL_REPRODUCE, GOAL_RESEARCH, GOAL_OTHER] as const;

type PageRef = Pick<Source, 'page' | 'page_label' | 'pages'>;
type StatusKey = 'searching' | 'quote' | 'quote-approx' | 'passage-start' | 'not-found';

const en = {
  locale: undefined as string | undefined,
  // header
  newConversation: 'Start a new conversation', languageSettings: 'Language', textSize: 'Text size',
  researchNote: 'Research-use note', downloadMenu: 'Download note or session log', openHistory: 'Open chat history',
  paperTitlePlaceholder: 'Paper title',
  welcome: ['Hello, Hongshan!', 'Let’s start reading a paper :)'],
  // goals and context
  goalQuestion: 'What would you like to learn?',
  goals: {
    [GOAL_OVERVIEW]: 'Get a general overview of this paper', [GOAL_REPRODUCE]: 'Reproduce the study or method',
    [GOAL_RESEARCH]: 'Explore potential use in my research', [GOAL_OTHER]: 'Other — type a goal in the chat',
  } as Record<string, string>,
  goalChip: (goal: string) => `Goal: ${goal}`,
  yourResearchSmall: 'YOUR RESEARCH', contextCompactTitle: 'Tell PaperLens about your research first',
  contextTitle: 'What is your research about?',
  contextHelp: 'Describe your research question, project or context in a few sentences. PaperLens uses it to judge relevance for your study.',
  contextPlaceholder: 'e.g. I am studying how difficulty curves in mobile puzzle games affect whether casual players keep playing…',
  skipForNow: 'Skip for now', saveContext: 'Save research context',
  researchContextSmall: 'YOUR RESEARCH CONTEXT',
  contextMissing: 'Not provided yet. PaperLens will ask for it before judging relevance to your research.',
  edit: 'Edit', addContext: 'Add research context',
  chooseQuestion: 'Choose a question to begin', orTypeOwn: '…or type your own question below.',
  typeGoal: 'Type your reading goal or first question below',
  starterQuestions: {
    [GOAL_OVERVIEW]: ["Summarise the paper's main argument.", 'What problem does this paper address?', 'What key concepts do I need to understand first?'],
    [GOAL_REPRODUCE]: ['What method or procedure does the paper use?', 'What data, participants or materials did the authors use?', 'What details would I need to reproduce this study?'],
    [GOAL_RESEARCH]: ["Summarise the paper's main argument.", 'Which ideas in this paper could be relevant to my research?', "What are the limitations of the paper's approach?"],
  } as Record<string, string[]>,
  // composer
  messageLabel: 'Message', send: 'Send message',
  placeholderNoPaper: 'Load a paper to start a conversation…', placeholderNoSession: 'Choose a reading goal first…',
  placeholderBusy: 'PaperLens is answering…', placeholderAsk: 'Ask about the paper…',
  goToQuestion: (n: number) => `Go to question ${n}`, jumpToQuestion: 'Jump to a question',
  criticalReview: 'Critical review', criticalReviewHint: 'Evaluate applicability to my research',
  resizePanels: 'Resize paper and conversation panels',
  // history
  historyTitle: 'Chat history', closeHistory: 'Close history', noSessions: 'No saved sessions yet.',
  currentSession: 'CURRENT SESSION', untitledPaper: 'Untitled paper',
  deleteConfirm: 'Delete this session?', deleteHint: 'It disappears from your history. Its run log is kept for evaluation.',
  cancel: 'Cancel', delete: 'Delete', deleteSession: 'Delete session', deleteSessionOf: (title: string) => `Delete session: ${title}`,
  // menus
  textSizeMenu: 'TEXT SIZE · CONVERSATION PANE', sizes: { standard: 'Standard', large: 'Large', larger: 'Larger' },
  downloadTitle: 'DOWNLOAD', noteMd: 'Research-use note (.md)', noteMdDesc: 'Your note as a Markdown document',
  noteMdDisabled: 'Draft the note on the note page first', logJson: 'Session log (.json)',
  logJsonDesc: 'Full conversation, sources and run log, for evaluation',
  languageTitle: 'Language of the interface and of PaperLens’s answers', languageDefault: 'default',
  languageNote: 'Paper text and quotes stay in the original language. You can also ask PaperLens in the chat to answer in another language.',
  // upload and indexing
  chooseFile: 'Choose a PDF file', uploading: 'Uploading…', dropHere: ['Drop a PDF here', 'or click to browse'],
  urlPlaceholder: 'Paste a direct PDF or arXiv link', urlLabel: 'Paper URL', open: 'Open', uploadHint: 'Text-based PDF · arXiv link',
  notPdf: 'Please choose a PDF file.',
  preparing: 'Preparing your paper…', preparingHint: 'Long papers can take a minute.',
  prepFailed: 'This paper could not be prepared',
  failedStage: {
    parsing: 'Failed while reading the text of the PDF.', indexing: 'Failed while building the search index.',
    summarizing: 'Failed while writing the overview of the paper.',
  } as Record<string, string>,
  uploadDifferent: 'Upload a different PDF', retry: 'Retry',
  backendUnreachable: 'Cannot reach the PaperLens backend. Start it with `npm run backend`, then retry.',
  // source panel and PDF viewer
  paperViewer: 'Paper viewer', sourceN: (n: number) => `Source ${n}`, noteEvidence: 'Note evidence', citedPassage: 'Cited passage',
  closePassage: 'Close cited passage', showPassage: 'Show passage', hidePassage: 'Hide passage',
  summaryNote: 'PaperLens-generated summary of these pages, not the authors’ words. Open a page to read the original text.',
  status: {
    searching: 'Locating…', quote: '',
    'quote-approx': 'Approximate highlight: the PDF text differs slightly.',
    'passage-start': 'No verified quote for this source: the start of the passage is highlighted.',
    'not-found': 'Position not found on this page. The extracted passage is shown below.',
  } as Record<StatusKey, string>,
  pdfControls: 'PDF controls', prevPage: 'Previous page', nextPage: 'Next page', pageNumber: 'Page number',
  zoomOut: 'Zoom out', zoomIn: 'Zoom in', fit: 'Fit', fitTitle: 'Fit to width',
  openExternal: 'Open in the browser’s PDF viewer (search, print)', downloadPdf: 'Download PDF', loadingPdf: 'Loading PDF…',
  pdfError: (message: string) => `This PDF could not be displayed here (${message}).`, openInBrowser: 'Open it in the browser’s viewer',
  pageText(source: PageRef) {
    if (source.pages && source.pages.length > 1) return `PDF pp. ${source.pages[0]}–${source.pages[source.pages.length - 1]}`;
    if (source.page == null) return 'page unknown';
    const printed = source.page_label && source.page_label !== String(source.page) ? ` (printed p. ${source.page_label})` : '';
    return `PDF p. ${source.page}${printed}`;
  },
  pageButton: (page: number) => `PDF p. ${page}`,
  // conversation
  kinds: {
    paper: 'From the paper', explanation: 'Explanation', example: 'Illustrative example · not from the paper',
    inference: 'PaperLens inference', research_use: 'For your research', limitation: 'Limitation / uncertainty',
  } as Record<SectionKind, string>,
  criticalReviewRequestLabel: 'Critical review request', judgmentLabel: 'My research-use decision',
  criticalReviewRequest: 'Critically review whether the idea or method we have been discussing is applicable to my research.',
  judgmentMessage: (verdict: string, rationale: string) => `My verdict: ${verdict}\nMy rationale: ${rationale}`,
  evidenceInsufficient: 'The passages PaperLens found are not enough to confirm this. This does not mean the paper never discusses it — try a more specific question.',
  evidencePartial: 'Only partly supported by the passages found. Check the sources before relying on it.',
  evidenceNoPaper: 'No original paper passage is cited for this answer.',
  suggestionTitle: 'PAPERLENS SUGGESTION · NOT YOUR DECISION', paperlensAsks: 'PAPERLENS ASKS',
  fromThePaper: 'FROM THE PAPER', summariesTitle: 'PAPERLENS SUMMARIES · NOT THE AUTHORS’ WORDS', unverifiedId: 'UNVERIFIED ID',
  answerLayers: 'Expandable answer layers', followUp: 'FOLLOW UP',
  couldNotAnswer: (error: string) => `PaperLens could not answer: ${error}`, thinking: 'PaperLens is reading the paper…',
  // judgment
  learnerJudgment: 'LEARNER JUDGMENT', yourDecision: 'Your decision:', createNote: 'Create research-use note', revise: 'Revise my decision',
  howUse: 'How will you use this idea?',
  judgmentIntro: (hasSuggestion: boolean) => `PaperLens has organised the evidence${hasSuggestion ? ' and made a suggestion above' : ''}. The final research-use decision and the reasons are yours.`,
  verdicts: {
    'Use as proposed': 'Use as proposed', 'Use with adaptations': 'Use with adaptations', 'Do not use': 'Do not use',
    'Need more evidence': 'Need more evidence',
  } as Record<Verdict, string>,
  yourReason: 'Your reason, in your own words',
  rationalePlaceholder: 'Why did you choose this? Which evidence or limitation matters most for your study?',
  recordDecision: 'Record my decision',
  // notes
  backToConversation: 'Back to conversation', noteHeading: 'RESEARCH-USE NOTE', yourNote: 'Your note', noNoteYet: 'No note yet',
  notesIntro: 'A decision-focused record of the selected idea, its evidence, possible use and unresolved uncertainty — drafted from this session and editable by you.',
  readingGoal: 'READING GOAL', myResearch: 'MY RESEARCH', noGoal: 'No reading goal selected', notProvided: 'Not provided',
  drafting: 'Drafting from this session…', draftNote: 'Draft a note from this session',
  askFirst: 'Ask PaperLens at least one question about the paper first.',
  selectedIdea: 'Selected idea', myJudgment: 'My judgment', myFinalJudgment: 'MY FINAL JUDGMENT',
  notDecided: 'Not decided yet — record your decision after the critical review.', myReason: 'MY REASON',
  paperlensSuggested: 'PAPERLENS SUGGESTED', noReview: 'No critical review in this session.',
  evidenceAndUse: 'Evidence and research use', supportingEvidence: 'Supporting evidence', noEvidence: 'No cited evidence in this session.',
  possibleUse: 'Possible use in my research', adaptations: 'Required adaptations & uncertainties', nextActions: 'Next actions',
  unsaved: 'Unsaved changes', editedSaved: 'Edited by you · saved', draftedBy: 'Drafted by PaperLens from this session',
  redraft: 'Re-draft from session', saveAndDownload: 'Save & download .md', downloadMd: 'Download .md', saveNote: 'Save note',
};

export type Strings = typeof en;

const zhHans: Strings = {
  locale: 'zh-CN',
  newConversation: '开始新对话', languageSettings: '语言', textSize: '字号', researchNote: '研究应用笔记',
  downloadMenu: '下载笔记或会话日志', openHistory: '打开对话历史', paperTitlePlaceholder: '论文标题',
  welcome: ['你好，Hongshan！', '开始读一篇论文吧 :)'],
  goalQuestion: '你想了解什么？',
  goals: { [GOAL_OVERVIEW]: '了解这篇论文的概况', [GOAL_REPRODUCE]: '复现研究或方法', [GOAL_RESEARCH]: '探索在我研究中的潜在用途', [GOAL_OTHER]: '其他——在对话中输入你的目标' },
  goalChip: (goal) => `目标：${goal}`,
  yourResearchSmall: '你的研究', contextCompactTitle: '请先介绍一下你的研究', contextTitle: '你的研究是关于什么的？',
  contextHelp: '用几句话描述你的研究问题、项目或背景。PaperLens 会据此判断论文与你的研究是否相关。',
  contextPlaceholder: '例如：我在研究手机益智游戏的难度曲线如何影响休闲玩家是否继续玩……',
  skipForNow: '暂时跳过', saveContext: '保存研究背景',
  researchContextSmall: '你的研究背景', contextMissing: '尚未填写。PaperLens 在判断与你研究的相关性之前会先询问。',
  edit: '编辑', addContext: '添加研究背景',
  chooseQuestion: '选一个问题开始', orTypeOwn: '……或在下方输入你自己的问题。', typeGoal: '在下方输入你的阅读目标或第一个问题',
  starterQuestions: {
    [GOAL_OVERVIEW]: ['概括这篇论文的主要论点。', '这篇论文要解决什么问题？', '我需要先理解哪些关键概念？'],
    [GOAL_REPRODUCE]: ['论文使用了什么方法或流程？', '作者使用了哪些数据、参与者或材料？', '复现这项研究需要哪些细节？'],
    [GOAL_RESEARCH]: ['概括这篇论文的主要论点。', '论文中哪些想法可能与我的研究相关？', '论文方法有哪些局限？'],
  },
  messageLabel: '消息', send: '发送',
  placeholderNoPaper: '先载入一篇论文再开始对话……', placeholderNoSession: '请先选择阅读目标……',
  placeholderBusy: 'PaperLens 正在回答……', placeholderAsk: '就这篇论文提问……',
  goToQuestion: (n) => `跳到第 ${n} 个问题`, jumpToQuestion: '跳到某个问题',
  criticalReview: '批判性评估', criticalReviewHint: '评估是否适用于我的研究', resizePanels: '调整论文和对话面板的宽度',
  historyTitle: '对话历史', closeHistory: '关闭历史', noSessions: '还没有保存的会话。', currentSession: '当前会话', untitledPaper: '未命名论文',
  deleteConfirm: '删除这个会话？', deleteHint: '它会从历史中消失，运行日志会保留用于评估。',
  cancel: '取消', delete: '删除', deleteSession: '删除会话', deleteSessionOf: (title) => `删除会话：${title}`,
  textSizeMenu: '字号 · 对话区', sizes: { standard: '标准', large: '大', larger: '更大' },
  downloadTitle: '下载', noteMd: '研究应用笔记（.md）', noteMdDesc: '以 Markdown 文档保存你的笔记', noteMdDisabled: '请先在笔记页起草笔记',
  logJson: '会话日志（.json）', logJsonDesc: '完整对话、来源和运行日志，用于评估',
  languageTitle: '界面和 PaperLens 回答使用的语言', languageDefault: '默认',
  languageNote: '论文原文和引文保持原语言。你也可以在对话中直接要求 PaperLens 用其他语言回答。',
  chooseFile: '选择 PDF 文件', uploading: '正在上传……', dropHere: ['把 PDF 拖到这里', '或点击选择文件'],
  urlPlaceholder: '粘贴 PDF 直链或 arXiv 链接', urlLabel: '论文链接', open: '打开', uploadHint: '文字版 PDF · arXiv 链接', notPdf: '请选择 PDF 文件。',
  preparing: '正在准备论文……', preparingHint: '较长的论文可能需要一分钟左右。', prepFailed: '这篇论文无法完成准备',
  failedStage: { parsing: '读取 PDF 文字时失败。', indexing: '建立检索索引时失败。', summarizing: '生成论文概览时失败。' },
  uploadDifferent: '换一份 PDF', retry: '重试',
  backendUnreachable: '无法连接 PaperLens 后端。请先运行 `npm run backend`，然后重试。',
  paperViewer: '论文查看器', sourceN: (n) => `来源 ${n}`, noteEvidence: '笔记证据', citedPassage: '引用段落',
  closePassage: '关闭引用段落', showPassage: '查看段落', hidePassage: '收起段落',
  summaryNote: '这是 PaperLens 对这几页生成的摘要，不是作者原话。打开页面可阅读原文。',
  status: {
    searching: '正在定位……', quote: '', 'quote-approx': '近似高亮：PDF 文字与提取文字略有不同。',
    'passage-start': '此来源没有经过核对的引文，已高亮段落开头。', 'not-found': '在本页没有找到准确位置，提取出的段落见下方。',
  },
  pdfControls: 'PDF 控制', prevPage: '上一页', nextPage: '下一页', pageNumber: '页码', zoomOut: '缩小', zoomIn: '放大',
  fit: '适合宽度', fitTitle: '适合宽度', openExternal: '在浏览器自带的 PDF 查看器中打开（搜索、打印）', downloadPdf: '下载 PDF',
  loadingPdf: '正在载入 PDF……', pdfError: (message) => `这个 PDF 无法在此显示（${message}）。`, openInBrowser: '在浏览器查看器中打开',
  pageText(source) {
    if (source.pages && source.pages.length > 1) return `PDF 第 ${source.pages[0]}–${source.pages[source.pages.length - 1]} 页`;
    if (source.page == null) return '页码未知';
    const printed = source.page_label && source.page_label !== String(source.page) ? `（印刷页码 ${source.page_label}）` : '';
    return `PDF 第 ${source.page} 页${printed}`;
  },
  pageButton: (page) => `PDF 第 ${page} 页`,
  kinds: { paper: '来自论文', explanation: '解释', example: '示例 · 不是来自论文', inference: 'PaperLens 推断', research_use: '对你的研究', limitation: '局限 / 不确定' },
  criticalReviewRequestLabel: '批判性评估请求', judgmentLabel: '我的研究应用决定',
  criticalReviewRequest: '请批判性地评估我们讨论的想法或方法是否适用于我的研究。',
  judgmentMessage: (verdict, rationale) => `我的判断：${verdict}\n我的理由：${rationale}`,
  evidenceInsufficient: 'PaperLens 找到的段落不足以确认这一点。这不代表论文没有讨论它——可以试试更具体的问题。',
  evidencePartial: '找到的段落只能部分支持这个回答。依赖它之前请先查看来源。',
  evidenceNoPaper: '这个回答没有引用论文原文段落。',
  suggestionTitle: 'PAPERLENS 的建议 · 不是你的决定', paperlensAsks: 'PAPERLENS 想问',
  fromThePaper: '来自论文', summariesTitle: 'PAPERLENS 摘要 · 不是作者原话', unverifiedId: '未核实的 ID',
  answerLayers: '可展开的回答内容', followUp: '继续追问',
  couldNotAnswer: (error) => `PaperLens 无法回答：${error}`, thinking: 'PaperLens 正在阅读论文……',
  learnerJudgment: '学习者的判断', yourDecision: '你的决定：', createNote: '创建研究应用笔记', revise: '修改我的决定',
  howUse: '你打算如何使用这个想法？',
  judgmentIntro: (hasSuggestion) => `PaperLens 已整理了证据${hasSuggestion ? '，并在上方给出了建议' : ''}。最终的研究应用决定和理由由你来定。`,
  verdicts: { 'Use as proposed': '按原样使用', 'Use with adaptations': '调整后使用', 'Do not use': '不使用', 'Need more evidence': '需要更多证据' },
  yourReason: '用你自己的话写下理由', rationalePlaceholder: '你为什么这样选择？哪条证据或局限对你的研究最重要？', recordDecision: '记录我的决定',
  backToConversation: '返回对话', noteHeading: '研究应用笔记', yourNote: '你的笔记', noNoteYet: '还没有笔记',
  notesIntro: '围绕决定的记录：选定的想法、证据、可能的用途和尚未解决的不确定性——根据本次会话起草，你可以编辑。',
  readingGoal: '阅读目标', myResearch: '我的研究', noGoal: '未选择阅读目标', notProvided: '未提供',
  drafting: '正在根据本次会话起草……', draftNote: '根据本次会话起草笔记', askFirst: '请先就论文向 PaperLens 提至少一个问题。',
  selectedIdea: '选定的想法', myJudgment: '我的判断', myFinalJudgment: '我的最终判断', notDecided: '尚未决定——请在批判性评估之后记录你的决定。',
  myReason: '我的理由', paperlensSuggested: 'PAPERLENS 的建议', noReview: '本次会话没有进行批判性评估。',
  evidenceAndUse: '证据与研究用途', supportingEvidence: '支持证据', noEvidence: '本次会话没有引用证据。',
  possibleUse: '在我研究中的可能用途', adaptations: '需要的调整与不确定之处', nextActions: '下一步',
  unsaved: '有未保存的修改', editedSaved: '已由你编辑 · 已保存', draftedBy: '由 PaperLens 根据本次会话起草',
  redraft: '根据会话重新起草', saveAndDownload: '保存并下载 .md', downloadMd: '下载 .md', saveNote: '保存笔记',
};

const zhHant: Strings = {
  locale: 'zh-TW',
  newConversation: '開始新對話', languageSettings: '語言', textSize: '字級', researchNote: '研究應用筆記',
  downloadMenu: '下載筆記或對話紀錄', openHistory: '開啟對話歷史', paperTitlePlaceholder: '論文標題',
  welcome: ['你好，Hongshan！', '開始讀一篇論文吧 :)'],
  goalQuestion: '你想了解什麼？',
  goals: { [GOAL_OVERVIEW]: '了解這篇論文的概況', [GOAL_REPRODUCE]: '重現研究或方法', [GOAL_RESEARCH]: '探索在我研究中的潛在用途', [GOAL_OTHER]: '其他——在對話中輸入你的目標' },
  goalChip: (goal) => `目標：${goal}`,
  yourResearchSmall: '你的研究', contextCompactTitle: '請先介紹一下你的研究', contextTitle: '你的研究是關於什麼的？',
  contextHelp: '用幾句話描述你的研究問題、專案或背景。PaperLens 會據此判斷論文與你的研究是否相關。',
  contextPlaceholder: '例如：我在研究手機益智遊戲的難度曲線如何影響休閒玩家是否繼續玩……',
  skipForNow: '暫時略過', saveContext: '儲存研究背景',
  researchContextSmall: '你的研究背景', contextMissing: '尚未填寫。PaperLens 在判斷與你研究的相關性之前會先詢問。',
  edit: '編輯', addContext: '新增研究背景',
  chooseQuestion: '選一個問題開始', orTypeOwn: '……或在下方輸入你自己的問題。', typeGoal: '在下方輸入你的閱讀目標或第一個問題',
  starterQuestions: {
    [GOAL_OVERVIEW]: ['概括這篇論文的主要論點。', '這篇論文要解決什麼問題？', '我需要先理解哪些關鍵概念？'],
    [GOAL_REPRODUCE]: ['論文使用了什麼方法或流程？', '作者使用了哪些資料、參與者或材料？', '重現這項研究需要哪些細節？'],
    [GOAL_RESEARCH]: ['概括這篇論文的主要論點。', '論文中哪些想法可能與我的研究相關？', '論文方法有哪些侷限？'],
  },
  messageLabel: '訊息', send: '傳送',
  placeholderNoPaper: '先載入一篇論文再開始對話……', placeholderNoSession: '請先選擇閱讀目標……',
  placeholderBusy: 'PaperLens 正在回答……', placeholderAsk: '就這篇論文提問……',
  goToQuestion: (n) => `跳到第 ${n} 個問題`, jumpToQuestion: '跳到某個問題',
  criticalReview: '批判性評估', criticalReviewHint: '評估是否適用於我的研究', resizePanels: '調整論文和對話面板的寬度',
  historyTitle: '對話歷史', closeHistory: '關閉歷史', noSessions: '還沒有儲存的對話。', currentSession: '目前對話', untitledPaper: '未命名論文',
  deleteConfirm: '刪除這個對話？', deleteHint: '它會從歷史中消失，執行紀錄會保留用於評估。',
  cancel: '取消', delete: '刪除', deleteSession: '刪除對話', deleteSessionOf: (title) => `刪除對話：${title}`,
  textSizeMenu: '字級 · 對話區', sizes: { standard: '標準', large: '大', larger: '更大' },
  downloadTitle: '下載', noteMd: '研究應用筆記（.md）', noteMdDesc: '以 Markdown 文件儲存你的筆記', noteMdDisabled: '請先在筆記頁起草筆記',
  logJson: '對話紀錄（.json）', logJsonDesc: '完整對話、來源和執行紀錄，用於評估',
  languageTitle: '介面和 PaperLens 回答使用的語言', languageDefault: '預設',
  languageNote: '論文原文和引文保持原語言。你也可以在對話中直接要求 PaperLens 用其他語言回答。',
  chooseFile: '選擇 PDF 檔案', uploading: '正在上傳……', dropHere: ['把 PDF 拖到這裡', '或點擊選擇檔案'],
  urlPlaceholder: '貼上 PDF 直接連結或 arXiv 連結', urlLabel: '論文連結', open: '開啟', uploadHint: '文字版 PDF · arXiv 連結', notPdf: '請選擇 PDF 檔案。',
  preparing: '正在準備論文……', preparingHint: '較長的論文可能需要一分鐘左右。', prepFailed: '這篇論文無法完成準備',
  failedStage: { parsing: '讀取 PDF 文字時失敗。', indexing: '建立檢索索引時失敗。', summarizing: '產生論文概覽時失敗。' },
  uploadDifferent: '換一份 PDF', retry: '重試',
  backendUnreachable: '無法連線到 PaperLens 後端。請先執行 `npm run backend`，然後重試。',
  paperViewer: '論文檢視器', sourceN: (n) => `來源 ${n}`, noteEvidence: '筆記證據', citedPassage: '引用段落',
  closePassage: '關閉引用段落', showPassage: '查看段落', hidePassage: '收起段落',
  summaryNote: '這是 PaperLens 對這幾頁產生的摘要，不是作者原話。開啟頁面可閱讀原文。',
  status: {
    searching: '正在定位……', quote: '', 'quote-approx': '近似標示：PDF 文字與擷取文字略有不同。',
    'passage-start': '此來源沒有經過核對的引文，已標示段落開頭。', 'not-found': '在本頁沒有找到準確位置，擷取出的段落見下方。',
  },
  pdfControls: 'PDF 控制', prevPage: '上一頁', nextPage: '下一頁', pageNumber: '頁碼', zoomOut: '縮小', zoomIn: '放大',
  fit: '符合寬度', fitTitle: '符合寬度', openExternal: '在瀏覽器內建的 PDF 檢視器中開啟（搜尋、列印）', downloadPdf: '下載 PDF',
  loadingPdf: '正在載入 PDF……', pdfError: (message) => `這個 PDF 無法在此顯示（${message}）。`, openInBrowser: '在瀏覽器檢視器中開啟',
  pageText(source) {
    if (source.pages && source.pages.length > 1) return `PDF 第 ${source.pages[0]}–${source.pages[source.pages.length - 1]} 頁`;
    if (source.page == null) return '頁碼未知';
    const printed = source.page_label && source.page_label !== String(source.page) ? `（印刷頁碼 ${source.page_label}）` : '';
    return `PDF 第 ${source.page} 頁${printed}`;
  },
  pageButton: (page) => `PDF 第 ${page} 頁`,
  kinds: { paper: '來自論文', explanation: '解釋', example: '範例 · 不是來自論文', inference: 'PaperLens 推論', research_use: '對你的研究', limitation: '侷限 / 不確定' },
  criticalReviewRequestLabel: '批判性評估請求', judgmentLabel: '我的研究應用決定',
  criticalReviewRequest: '請批判性地評估我們討論的想法或方法是否適用於我的研究。',
  judgmentMessage: (verdict, rationale) => `我的判斷：${verdict}\n我的理由：${rationale}`,
  evidenceInsufficient: 'PaperLens 找到的段落不足以確認這一點。這不代表論文沒有討論它——可以試試更具體的問題。',
  evidencePartial: '找到的段落只能部分支持這個回答。依賴它之前請先查看來源。',
  evidenceNoPaper: '這個回答沒有引用論文原文段落。',
  suggestionTitle: 'PAPERLENS 的建議 · 不是你的決定', paperlensAsks: 'PAPERLENS 想問',
  fromThePaper: '來自論文', summariesTitle: 'PAPERLENS 摘要 · 不是作者原話', unverifiedId: '未核實的 ID',
  answerLayers: '可展開的回答內容', followUp: '繼續追問',
  couldNotAnswer: (error) => `PaperLens 無法回答：${error}`, thinking: 'PaperLens 正在閱讀論文……',
  learnerJudgment: '學習者的判斷', yourDecision: '你的決定：', createNote: '建立研究應用筆記', revise: '修改我的決定',
  howUse: '你打算如何使用這個想法？',
  judgmentIntro: (hasSuggestion) => `PaperLens 已整理了證據${hasSuggestion ? '，並在上方提出了建議' : ''}。最終的研究應用決定和理由由你來定。`,
  verdicts: { 'Use as proposed': '按原樣使用', 'Use with adaptations': '調整後使用', 'Do not use': '不使用', 'Need more evidence': '需要更多證據' },
  yourReason: '用你自己的話寫下理由', rationalePlaceholder: '你為什麼這樣選擇？哪條證據或侷限對你的研究最重要？', recordDecision: '記錄我的決定',
  backToConversation: '返回對話', noteHeading: '研究應用筆記', yourNote: '你的筆記', noNoteYet: '還沒有筆記',
  notesIntro: '圍繞決定的紀錄：選定的想法、證據、可能的用途和尚未解決的不確定性——根據本次對話起草，你可以編輯。',
  readingGoal: '閱讀目標', myResearch: '我的研究', noGoal: '未選擇閱讀目標', notProvided: '未提供',
  drafting: '正在根據本次對話起草……', draftNote: '根據本次對話起草筆記', askFirst: '請先就論文向 PaperLens 提至少一個問題。',
  selectedIdea: '選定的想法', myJudgment: '我的判斷', myFinalJudgment: '我的最終判斷', notDecided: '尚未決定——請在批判性評估之後記錄你的決定。',
  myReason: '我的理由', paperlensSuggested: 'PAPERLENS 的建議', noReview: '本次對話沒有進行批判性評估。',
  evidenceAndUse: '證據與研究用途', supportingEvidence: '支持證據', noEvidence: '本次對話沒有引用證據。',
  possibleUse: '在我研究中的可能用途', adaptations: '需要的調整與不確定之處', nextActions: '下一步',
  unsaved: '有未儲存的修改', editedSaved: '已由你編輯 · 已儲存', draftedBy: '由 PaperLens 根據本次對話起草',
  redraft: '根據對話重新起草', saveAndDownload: '儲存並下載 .md', downloadMd: '下載 .md', saveNote: '儲存筆記',
};

const ja: Strings = {
  locale: 'ja-JP',
  newConversation: '新しい会話を始める', languageSettings: '言語', textSize: '文字サイズ', researchNote: '研究活用ノート',
  downloadMenu: 'ノートまたはセッションログをダウンロード', openHistory: '会話履歴を開く', paperTitlePlaceholder: '論文タイトル',
  welcome: ['こんにちは、Hongshan さん！', '論文を読み始めましょう :)'],
  goalQuestion: '何を知りたいですか？',
  goals: { [GOAL_OVERVIEW]: '論文の全体像をつかむ', [GOAL_REPRODUCE]: '研究や手法を再現する', [GOAL_RESEARCH]: '自分の研究での活用を探る', [GOAL_OTHER]: 'その他 — チャットで目的を入力' },
  goalChip: (goal) => `目的：${goal}`,
  yourResearchSmall: 'あなたの研究', contextCompactTitle: 'まずあなたの研究について教えてください', contextTitle: 'どんな研究をしていますか？',
  contextHelp: '研究課題・プロジェクト・背景を数文で書いてください。PaperLens はそれをもとに、論文があなたの研究に関係するかを判断します。',
  contextPlaceholder: '例：スマホのパズルゲームの難易度曲線が、カジュアルプレイヤーの継続にどう影響するかを研究しています……',
  skipForNow: '今はスキップ', saveContext: '研究背景を保存',
  researchContextSmall: 'あなたの研究背景', contextMissing: 'まだ入力されていません。研究との関連を判断する前に PaperLens が尋ねます。',
  edit: '編集', addContext: '研究背景を追加',
  chooseQuestion: '最初の質問を選んでください', orTypeOwn: '……または下に自分の質問を入力してください。', typeGoal: '下に読む目的か最初の質問を入力してください',
  starterQuestions: {
    [GOAL_OVERVIEW]: ['この論文の主な主張を要約してください。', 'この論文はどんな問題に取り組んでいますか？', '最初に理解すべき重要な概念は何ですか？'],
    [GOAL_REPRODUCE]: ['論文ではどんな手法や手順を使っていますか？', '著者はどんなデータ・参加者・材料を使いましたか？', 'この研究を再現するにはどんな詳細が必要ですか？'],
    [GOAL_RESEARCH]: ['この論文の主な主張を要約してください。', 'この論文のどのアイデアが自分の研究に関係しそうですか？', '論文のアプローチの限界は何ですか？'],
  },
  messageLabel: 'メッセージ', send: '送信',
  placeholderNoPaper: '論文を読み込んでから会話を始めてください……', placeholderNoSession: 'まず読む目的を選んでください……',
  placeholderBusy: 'PaperLens が回答中……', placeholderAsk: '論文について質問……',
  goToQuestion: (n) => `${n} 番目の質問へ移動`, jumpToQuestion: '質問へ移動',
  criticalReview: '批判的レビュー', criticalReviewHint: '自分の研究への適用可能性を評価', resizePanels: '論文と会話のパネル幅を調整',
  historyTitle: '会話履歴', closeHistory: '履歴を閉じる', noSessions: '保存されたセッションはまだありません。', currentSession: '現在のセッション', untitledPaper: '無題の論文',
  deleteConfirm: 'このセッションを削除しますか？', deleteHint: '履歴から消えます。実行ログは評価用に保存されます。',
  cancel: 'キャンセル', delete: '削除', deleteSession: 'セッションを削除', deleteSessionOf: (title) => `セッションを削除：${title}`,
  textSizeMenu: '文字サイズ · 会話エリア', sizes: { standard: '標準', large: '大', larger: '特大' },
  downloadTitle: 'ダウンロード', noteMd: '研究活用ノート（.md）', noteMdDesc: 'ノートを Markdown 文書として保存', noteMdDisabled: '先にノートページでノートを作成してください',
  logJson: 'セッションログ（.json）', logJsonDesc: '会話全体・出典・実行ログ（評価用）',
  languageTitle: 'インターフェースと PaperLens の回答の言語', languageDefault: 'デフォルト',
  languageNote: '論文本文と引用は元の言語のままです。チャットで別の言語での回答を頼むこともできます。',
  chooseFile: 'PDF ファイルを選択', uploading: 'アップロード中……', dropHere: ['ここに PDF をドロップ', 'またはクリックして選択'],
  urlPlaceholder: 'PDF の直接リンクか arXiv のリンクを貼り付け', urlLabel: '論文の URL', open: '開く', uploadHint: 'テキスト形式の PDF · arXiv リンク', notPdf: 'PDF ファイルを選んでください。',
  preparing: '論文を準備しています……', preparingHint: '長い論文は 1 分ほどかかることがあります。', prepFailed: 'この論文を準備できませんでした',
  failedStage: { parsing: 'PDF のテキスト読み取り中に失敗しました。', indexing: '検索インデックスの作成中に失敗しました。', summarizing: '論文の概要作成中に失敗しました。' },
  uploadDifferent: '別の PDF をアップロード', retry: '再試行',
  backendUnreachable: 'PaperLens のバックエンドに接続できません。`npm run backend` で起動してから再試行してください。',
  paperViewer: '論文ビューア', sourceN: (n) => `出典 ${n}`, noteEvidence: 'ノートの根拠', citedPassage: '引用箇所',
  closePassage: '引用箇所を閉じる', showPassage: '箇所を表示', hidePassage: '箇所を隠す',
  summaryNote: 'これらのページについて PaperLens が作成した要約で、著者の言葉ではありません。ページを開くと原文を読めます。',
  status: {
    searching: '位置を探しています……', quote: '', 'quote-approx': 'おおよそのハイライト：PDF の文字と抽出テキストが少し異なります。',
    'passage-start': 'この出典には確認済みの引用がないため、箇所の冒頭をハイライトしています。', 'not-found': 'このページで正確な位置が見つかりませんでした。抽出した箇所を下に表示します。',
  },
  pdfControls: 'PDF 操作', prevPage: '前のページ', nextPage: '次のページ', pageNumber: 'ページ番号', zoomOut: '縮小', zoomIn: '拡大',
  fit: '幅に合わせる', fitTitle: '幅に合わせる', openExternal: 'ブラウザの PDF ビューアで開く（検索・印刷）', downloadPdf: 'PDF をダウンロード',
  loadingPdf: 'PDF を読み込み中……', pdfError: (message) => `この PDF はここに表示できませんでした（${message}）。`, openInBrowser: 'ブラウザのビューアで開く',
  pageText(source) {
    if (source.pages && source.pages.length > 1) return `PDF ${source.pages[0]}–${source.pages[source.pages.length - 1]} ページ`;
    if (source.page == null) return 'ページ不明';
    const printed = source.page_label && source.page_label !== String(source.page) ? `（印刷ページ ${source.page_label}）` : '';
    return `PDF ${source.page} ページ${printed}`;
  },
  pageButton: (page) => `PDF ${page} ページ`,
  kinds: { paper: '論文より', explanation: '説明', example: '例 · 論文からではありません', inference: 'PaperLens の推論', research_use: 'あなたの研究に', limitation: '限界 / 不確かさ' },
  criticalReviewRequestLabel: '批判的レビューの依頼', judgmentLabel: '研究活用についての判断',
  criticalReviewRequest: 'これまで話してきたアイデアや手法が自分の研究に適用できるか、批判的にレビューしてください。',
  judgmentMessage: (verdict, rationale) => `私の判断：${verdict}\n理由：${rationale}`,
  evidenceInsufficient: 'PaperLens が見つけた箇所だけでは確認できません。論文が扱っていないという意味ではないので、より具体的に質問してみてください。',
  evidencePartial: '見つかった箇所による裏付けは一部だけです。頼る前に出典を確認してください。',
  evidenceNoPaper: 'この回答には論文本文の引用がありません。',
  suggestionTitle: 'PAPERLENS の提案 · あなたの判断ではありません', paperlensAsks: 'PAPERLENS からの質問',
  fromThePaper: '論文より', summariesTitle: 'PAPERLENS の要約 · 著者の言葉ではありません', unverifiedId: '未確認の ID',
  answerLayers: '展開できる回答', followUp: '続けて質問',
  couldNotAnswer: (error) => `PaperLens は回答できませんでした：${error}`, thinking: 'PaperLens が論文を読んでいます……',
  learnerJudgment: '学習者の判断', yourDecision: 'あなたの判断：', createNote: '研究活用ノートを作成', revise: '判断を見直す',
  howUse: 'このアイデアをどう使いますか？',
  judgmentIntro: (hasSuggestion) => `PaperLens は根拠を整理しました${hasSuggestion ? '（上に提案もあります）' : ''}。研究での使い方の最終判断と理由はあなたが決めます。`,
  verdicts: { 'Use as proposed': '提案どおり使う', 'Use with adaptations': '調整して使う', 'Do not use': '使わない', 'Need more evidence': 'さらに根拠が必要' },
  yourReason: '理由を自分の言葉で', rationalePlaceholder: 'なぜこれを選びましたか？ どの根拠や限界があなたの研究にとって最も重要ですか？', recordDecision: '判断を記録',
  backToConversation: '会話に戻る', noteHeading: '研究活用ノート', yourNote: 'あなたのノート', noNoteYet: 'ノートはまだありません',
  notesIntro: '選んだアイデア、その根拠、活用の可能性、未解決の不確かさをまとめた判断のための記録です。このセッションから作成され、編集できます。',
  readingGoal: '読む目的', myResearch: '自分の研究', noGoal: '読む目的が選ばれていません', notProvided: '未入力',
  drafting: 'このセッションから作成中……', draftNote: 'このセッションからノートを作成', askFirst: 'まず論文について PaperLens に 1 つ以上質問してください。',
  selectedIdea: '選んだアイデア', myJudgment: '自分の判断', myFinalJudgment: '最終判断', notDecided: 'まだ判断していません — 批判的レビューの後に判断を記録してください。',
  myReason: '理由', paperlensSuggested: 'PAPERLENS の提案', noReview: 'このセッションでは批判的レビューを行っていません。',
  evidenceAndUse: '根拠と研究での活用', supportingEvidence: '裏付けとなる根拠', noEvidence: 'このセッションで引用された根拠はありません。',
  possibleUse: '自分の研究での活用可能性', adaptations: '必要な調整と不確かな点', nextActions: '次のアクション',
  unsaved: '未保存の変更があります', editedSaved: '編集済み · 保存しました', draftedBy: 'このセッションから PaperLens が作成',
  redraft: 'セッションから作り直す', saveAndDownload: '保存して .md をダウンロード', downloadMd: '.md をダウンロード', saveNote: 'ノートを保存',
};

export const STRINGS: Record<Language, Strings> = { English: en, '中文（简体）': zhHans, '中文（繁體）': zhHant, 日本語: ja };

export const I18nContext = createContext<Strings>(en);
export const useT = () => useContext(I18nContext);

/** Show a stored learner message in the interface language (the stored text itself stays as sent). */
export function displayUserMessage(t: Strings, mode: string, text: string): string {
  if (mode === 'critical_review') return t.criticalReviewRequest;
  if (mode === 'judgment_feedback') {
    const match = /^My verdict: (.*)\nMy rationale: ([\s\S]*)$/.exec(text);
    if (match) return t.judgmentMessage(t.verdicts[match[1] as Verdict] ?? match[1], match[2]);
  }
  return text;
}
