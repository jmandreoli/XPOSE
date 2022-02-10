/* Creation date:        2022-01-15
 * Contributors:         Jean-Marc Andreoli
 * Language:             javascript
 * Purpose:              XposeCalendar: a calendar manager based on Xpose (client side)
 */

class XposeCalendar {

  constructor (el,cal,xpose) {
    // el: element in the page
    // cal: argument to FullCalendar.Calendar; all sources (if any) should be specified in eventSources
    // xpose: object with fields id,url,sources
    el.innerHTML = ''

    var table = document.createElement('table')
    el.appendChild(table)
    var header = table.insertRow()
    header.style.fontSize = 'x-small'

    var evSource = {id:xpose.id,events:(x,success,failure)=>{return this.events(x,success,failure)}}
    if (cal.eventSources) {cal.eventSources.push(evSource)}
    else {cal.eventSources = [evSource]}
    this.el_calendar = document.createElement('div')
    this.el_calendar.className = 'calendar'
    el.appendChild(this.el_calendar)

    this.el_details = document.createElement('table')
    this.el_details.className = 'details'
    el.appendChild(this.el_details)

    header.insertCell().innerHTML = '<span>Jump to: </span>'
    var navigation = document.createElement('input')
    header.insertCell().appendChild(navigation)
    navigation.style.fontSize = 'x-small'
    navigation.type = 'date'
    navigation.addEventListener('blur',()=>{navigation.value=''},false)
    navigation.addEventListener('focus',()=>{navigation.value=this.calendar.view.currentStart},false)
    navigation.addEventListener('change',()=>{if(navigation.checkValidity()&&navigation.value){this.calendar.gotoDate(navigation.value)}},false)

    header.insertCell().innerHTML = '<span> Sources: </span>'
    var sources = []
    this.sourceMap = {}
    for (const src of xpose.sources) {
      sources.push(`'${src.id}'`)
      this.sourceMap[src.id] = src
      var td = header.insertCell(); td.innerHTML = src.id
      td.style.backgroundColor = src.options.backgroundColor||'black'
      td.style.color = src.options.textColor||'white'
    }
    this.sources = sources.join(',')

    header.insertCell().innerHTML = xpose.header||''

    this.url = xpose.url
    var sql = `SELECT min(start) as low,max(start) as high FROM Event WHERE source IN (${this.sources})`
    axios({url:`${this.url}?sql=${encodeURIComponent(sql)}`,headers:{'Cache-Control':'no-store'}}).then((resp)=>{
      var data = resp.data[0]
      var low = new Date(data.low); low.setMonth(0); low.setDate(1)
      var high = new Date(data.high); high.setFullYear(high.getFullYear()+1); high.setMonth(11); high.setDate(31)
      navigation.min = low.toISOString().substring(0,10)
      navigation.max = high.toISOString().substring(0,10)
      navigation.insertAdjacentHTML('afterend',`<span> (since ${low.getFullYear()})</span>`)
    })
    if (window.Showdown) {
      var conv = new showdown.Converter(window.Showdown)
      this.transformMarkdown = (a) => {for(const el of a){el.innerHTML = conv.makeHtml(el.innerHTML)}}
    }
    if (window.MathJax) {
      this.transformMath = (a) => {if(a.length)window.MathJax.typeset(a)}
    }
    this.currentYears = null
    this.calendar = new FullCalendar.Calendar(this.el_calendar,cal)
    return this.calendar
  }

  events (info,success,failure) {
    var start = new Date(info.start);start=start.getFullYear()
    var end = new Date(info.end);end.setSeconds(end.getSeconds()-1);end=end.getFullYear()
    var years = `${start}-${end}`
    if (this.currentYears==years||this.currentYears=='') {return}
    this.el_calendar.style.pointerEvents='none' // avoids bursts of updates, restored after ajax
    this.currentYears = ''
    console.log('Loading',years)
    var sql = `SELECT entry as oid,start,end,title,source,
      xpose_template('events/'||Entry.cat,'events/error','{"value":'||Entry.value||',"attach":"'||Entry.attach||'"}') as details FROM Event,Entry
      WHERE entry=Entry.oid AND start BETWEEN '${start}-01-01' AND '${end}-12-31' AND source IN (${this.sources}) ORDER BY start DESC
    `
    axios({url:`${this.url}?sql=${encodeURIComponent(sql)}`,headers:{'Cache-Control':'no-store'}}).
      finally(()=>this.el_calendar.style.pointerEvents='auto').
      then((resp)=>{success(this.process(resp.data));this.currentYears=years}).
      catch((error)=>{failure(error);this.el_details.innerHTML=`<pre>${error.message}\n${error.response?error.response.data:''}</pre>`})
  }

  process (data) {
    this.el_details.innerHTML = ''
    var events = data.map((row)=>this.process_row(row))
    if (this.transformMarkdown) { this.transformMarkdown(Array.from(this.el_details.getElementsByClassName('transform-markdown'))) }
    if (this.transformMath) { this.transformMath(Array.from(this.el_details.getElementsByClassName('transform-math'))) }
    return events
  }

  process_row (row) {
    var ev = {id:`EV-${row.oid}`,start:row.start,end:row.end,title:row.title,extendedProps:{source:row.source}}
    this.el_details.insertAdjacentHTML('beforeend',row.details)
    var tbody = this.el_details.lastElementChild
    tbody.id = ev.id
    var td = tbody.insertRow(0).insertCell()
    td.colSpan = 2; td.className = 'setting'
    var options = this.sourceMap[row.source].options
    for (const o in options) { ev[o] = options[o] }
    td.style.backgroundColor = options.backgroundColor||'black'
    td.style.color = options.textColor||'white'
    var extra = tbody.dataset.left||''
    var status = tbody.dataset.right||''
    if (status) {status = `<div class="status">${status}</div>`}
    td.innerHTML = `${this.formatSpan(row.start,row.end)} ${extra} ${status}`
    return ev
  }

  formatSpan (start,end) {
    const startDate = new Date(start)
    return (start.length==10)?
      (end==start)?
        startDate.toDateString(): // single day
        `${startDate.toDateString()} —— ${new Date(end).toDateString()}`: // multi-day
      `${startDate.toDateString()} at ${this.formatTime(startDate)}` // punctual
  }
  formatTime (t) {
    const m = t.getMinutes()
    return `${1+((t.getHours()-1)%12+12)%12}${m?':'+String(m).padStart(2,'0'):''}${t.getHours()<12?'am':'pm'}`
  }
}
