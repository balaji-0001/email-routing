export type Mail = {
  id: string; provider: string; account: string; sender: string; email: string;
  subject: string; preview: string; time: string; unread: boolean; star: boolean;
  priority: 'High' | 'Normal' | 'Low'; labels: string[]; attachment?: string;
  assigned: string; summary: string; sentiment: string;
};

export const mails: Mail[] = [
  { id:'m-1048',provider:'Gmail',account:'hello@northstar.studio',sender:'Maya Chen',email:'maya@fieldnotes.co',subject:'Re: Q3 brand direction — final files',preview:'The updated identity deck is ready for your review. I added the alternate lockup we discussed…',time:'10:42 AM',unread:true,star:true,priority:'High',labels:['Client','Design'],attachment:'Northstar-identity-v6.pdf',assigned:'Alex Morgan',summary:'Maya shared the final identity deck and is waiting on sign-off before the campaign handoff.',sentiment:'Positive'},
  { id:'m-1047',provider:'Microsoft 365',account:'support@northstar.studio',sender:'Owen Park',email:'owen.park@clearwater.io',subject:'Access issue after workspace migration',preview:'Hi team, our two new hires are still seeing the old permissions screen. Could you take a look…',time:'10:18 AM',unread:true,star:false,priority:'High',labels:['Support','Needs reply'],assigned:'Unassigned',summary:'Customer reports two new team members cannot access updated workspace permissions.',sentiment:'Concerned'},
  { id:'m-1046',provider:'IMAP',account:'ops@northstar.studio',sender:'Daniel Ruiz',email:'daniel@harborworks.com',subject:'Invoice 2841 / June services',preview:'Attached is the revised invoice with the PO number included. Let me know if accounting needs anything…',time:'9:56 AM',unread:false,star:false,priority:'Normal',labels:['Finance'],attachment:'Invoice-2841.pdf',assigned:'Priya Shah',summary:'Revised June services invoice attached with the requested purchase order number.',sentiment:'Neutral'},
  { id:'m-1045',provider:'Gmail',account:'hello@northstar.studio',sender:'Nina Williams',email:'nina@lumenhouse.com',subject:'Partnership launch timing',preview:'We’re aligned on the 18th. Can you confirm the newsletter goes out at 9am Pacific?',time:'9:31 AM',unread:true,star:false,priority:'Normal',labels:['Partnerships'],assigned:'Alex Morgan',summary:'Partner confirms launch date and needs confirmation of newsletter send time.',sentiment:'Positive'},
  { id:'m-1044',provider:'Microsoft 365',account:'support@northstar.studio',sender:'Elliot Brooks',email:'elliot@brightpath.org',subject:'Re: Renewal options for 2025',preview:'Thanks for laying out the options. The annual plan looks right — please send over the paperwork…',time:'Yesterday',unread:false,star:true,priority:'Low',labels:['Sales','Renewal'],assigned:'Jordan Lee',summary:'Prospect selected the annual plan and requests renewal paperwork.',sentiment:'Positive'},
  { id:'m-1043',provider:'Gmail',account:'hello@northstar.studio',sender:'Ava Thompson',email:'ava@pixelpress.com',subject:'Quick question about the press kit',preview:'Would you have a portrait crop of the founder photo? The current file is a little wide for our layout…',time:'Yesterday',unread:false,star:false,priority:'Low',labels:['Press'],assigned:'Unassigned',summary:'Press contact asks for a portrait crop of the founder photograph.',sentiment:'Neutral'},
  { id:'m-1042',provider:'IMAP',account:'ops@northstar.studio',sender:'Samir Patel',email:'samir@northstar.studio',subject:'Monday team notes',preview:'A few things from the planning session: we should move the review block earlier and revisit…',time:'Mon',unread:false,star:false,priority:'Normal',labels:['Internal'],assigned:'Priya Shah',summary:'Internal recap with proposed changes to the weekly planning schedule.',sentiment:'Neutral'},
  { id:'m-1041',provider:'Gmail',account:'hello@northstar.studio',sender:'Grace Kim',email:'grace@littleorchard.com',subject:'Website feedback — mobile navigation',preview:'The new menu feels much easier to use. One small thing: the cart button disappears on my iPhone…',time:'Mon',unread:false,star:false,priority:'Normal',labels:['Client','Product'],assigned:'Jordan Lee',summary:'Client likes the redesigned menu but reports a cart button issue on iPhone.',sentiment:'Positive'},
];

export const accounts = [
 {provider:'Gmail',address:'hello@northstar.studio',status:'Connected',sync:'Just now',count:'2,481',color:'#d95140'},
 {provider:'Microsoft 365',address:'support@northstar.studio',status:'Connected',sync:'2 min ago',count:'1,904',color:'#3478c7'},
 {provider:'IMAP / SMTP',address:'ops@northstar.studio',status:'Connected',sync:'5 min ago',count:'846',color:'#6172b8'}
];
export const team = [
 {name:'Alex Morgan',email:'alex@northstar.studio',role:'Admin',status:'Active',assigned:18,last:'Now',initials:'AM',tone:'blue'},
 {name:'Priya Shah',email:'priya@northstar.studio',role:'Manager',status:'Active',assigned:12,last:'8 min ago',initials:'PS',tone:'peach'},
 {name:'Jordan Lee',email:'jordan@northstar.studio',role:'Agent',status:'Active',assigned:9,last:'22 min ago',initials:'JL',tone:'mint'},
 {name:'Samir Patel',email:'samir@northstar.studio',role:'Agent',status:'Away',assigned:4,last:'1 hour ago',initials:'SP',tone:'lavender'}
];
export const navGroups = [
 {title:'WORKSPACE',items:[['/dashboard','Overview','LayoutDashboard'],['/inbox','Unified inbox','Inbox'],['/drafts','Drafts','FileEdit'],['/sent','Sent','Send'],['/starred','Starred','Star'],['/archive','Archive','Archive'],['/trash','Trash','Trash']]},
 {title:'ORGANIZE',items:[['/search','Search','Search'],['/labels','Labels','Tags'],['/folders','Folders','Folder'],['/contacts','Contacts','ContactRound'],['/templates','Templates','FileText'],['/notifications','Notifications','Bell']]},
 {title:'COLLABORATE',items:[['/team','Team','Users'],['/team/invite','Invite members','UserPlus'],['/team/roles','Roles & permissions','ShieldCheck'],['/assignment','Assignments','ListTodo'],['/internal-notes','Internal notes','StickyNote']]},
 {title:'CONNECTED',items:[['/accounts','Email accounts','Mail'],['/accounts/add','Add account','Plus']]},
 {title:'INTELLIGENCE',items:[['/ai','AI overview','Sparkles'],['/ai/summary','Summaries','AlignLeft'],['/ai/reply','Reply assist','MessageSquareText'],['/ai/classification','Classification','ScanSearch'],['/ai/priority-sentiment','Priority & sentiment','Gauge'],['/ai/routing','Smart routing','Route'],['/ai/auto-reply','Auto-reply','Bot']]},
 {title:'AUTOMATION',items:[['/automation','Rules','Workflow'],['/automation/assignment','Assignment rules','UserRoundCog'],['/automation/labels-priority','Labels & priority','Tags'],['/automation/scheduled-actions','Scheduled actions','CalendarClock'],['/webhooks','Webhooks','Webhook']]},
 {title:'PREFERENCES',items:[['/settings','Settings','Settings'],['/settings/ai','AI controls','Sparkles'],['/settings/automation','Automation','Workflow'],['/settings/workspace','Workspace','Building2'],['/settings/accounts','Accounts','Mail'],['/settings/profile','Profile','CircleUserRound'],['/settings/security','Security','LockKeyhole'],['/settings/usage','Usage','ChartNoAxesCombined'],['/settings/audit-logs','Audit log','ScrollText']]},
];
export const pageTitles: Record<string, string> = {
  '/dashboard':'Overview','/inbox':'Unified inbox','/drafts':'Drafts','/sent':'Sent',
  '/starred':'Starred','/archive':'Archive','/trash':'Trash','/search':'Search',
  '/labels':'Labels','/folders':'Folders','/contacts':'Contacts','/templates':'Templates',
  '/notifications':'Notifications','/team':'Team members','/team/invite':'Invite your team',
  '/team/roles':'Roles & permissions','/assignment':'Assignment queue','/internal-notes':'Internal notes',
  '/accounts':'Email accounts','/accounts/add':'Add an account','/accounts/connect/gmail':'Connect Gmail',
  '/accounts/connect/outlook':'Connect Microsoft 365','/accounts/connect/imap':'Connect IMAP / SMTP',
  '/ai':'AI workspace','/ai/summary':'AI summaries','/ai/reply':'Reply assistance',
  '/ai/classification':'Email classification','/ai/priority-sentiment':'Priority & sentiment',
  '/ai/routing':'Smart routing','/ai/auto-reply':'Auto-reply suggestions',
  '/automation':'Automation rules','/automation/assignment':'Assignment rules',
  '/automation/labels-priority':'Labels & priority','/automation/scheduled-actions':'Scheduled actions',
  '/webhooks':'Webhooks','/settings':'Settings','/settings/ai':'AI controls',
  '/settings/automation':'Automation controls','/settings/workspace':'Workspace settings',
  '/settings/accounts':'Account settings','/settings/profile':'Your profile','/settings/security':'Security',
  '/settings/usage':'Usage & plan','/settings/audit-logs':'Audit log','/compose':'New message',
};
export const pageDescriptions: Record<string, string> = {
  '/drafts':'Messages waiting for a little more of your attention.',
  '/sent':'A shared view of messages sent from every connected account.',
  '/starred':'The conversations your team marked to come back to.',
  '/archive':'Resolved conversations, kept close when you need them.',
  '/trash':'Items here are only removed from this prototype view.',
  '/search':'Search across every connected inbox and shared conversation.',
  '/labels':'One vocabulary for organizing mail across all accounts.',
  '/folders':'A single view of folders synced from your providers.',
  '/contacts':'People your team has emailed, gathered in one place.',
  '/templates':'Reusable replies that keep the team’s voice consistent.',
  '/notifications':'A quiet timeline of changes across your workspace.',
  '/team':'The people who keep Northstar moving.',
  '/team/roles':'Set a clear boundary around what each role can do.',
  '/assignment':'A live-looking snapshot of conversations that need an owner.',
  '/internal-notes':'Private context shared with teammates, never sent to customers.',
  '/accounts':'Three inboxes, one considered place to work.',
  '/ai':'Optional assistance, always under your team’s control.',
  '/automation':'Small rules for repeatable work. Nothing executes in this demo.',
  '/webhooks':'Manage endpoints that can receive workspace events.',
};
