/* Creation date:        2022-01-15
 * Contributors:         Jean-Marc Andreoli
 * Language:             javascript
 * Purpose:              DetailCalendar: a calendar manager based on FullCalendar
 */

class DetailedEventSource {
// An instance of this class creates a "detailed" Fullcalendar event source and adds it to a Fullcalendar calendar instance.
// It adds a header above the calendar element with global information about the source, and a table below the calendar element to hold the details of individual events.
// The details are given in the form of a list of tbody elements, one for each detailed event.
// Details are displayed only for the events of the current year of the calendar.
// No more than one detailed source should be added to a calendar, but a detailed source can contain multiple sub-sources.
//
// Parameters:
// * calendar: the target calendar
// * config: configuration of the detailed source (see below)
//
// Configuration:
// * id: detailed source id in the calendar (string)
// * sources: list of sub-sources of the detailed source, each with
//   * id: sub-source id
//   * options: a dictionary of options applied to the events from that sub-source
// * headers: additional headers (list of html strings)
// * span: total span of the detailed source, with
//   * low,high: start and end dates
// * events: a possibly asynchronous callback with two inputs (startYear,endYear) returning an array of all the events in that interval (see below)
//
// Event (returned by the events callback):
// * oid: event id (string or number)
// * start,end: start and end time of the event (Date or DateTime ISO-formatted strings)
// * title: short title (string)
// * source: sub-source id (string)
// * details: tbody html element giving details about the event, typically on two columns key-value (html string)

  constructor (calendar,config) {
    this.calendar = calendar

    const table = document.createElement('table')
    const header = table.insertRow()
    header.style.fontSize = 'x-small'
    calendar.el.before(table)

    this.el_details = document.createElement('table')
    this.el_details.className = 'calendar-details'
    calendar.el.after(this.el_details)

    {
      const navigation = header.insertCell()
      const year = addElement(navigation,'select',{style:'font-size:x-small;'})
      const month = addElement(navigation,'select',{style:'display:none;position:absolute;z-index:100;font-size:x-small;',size:12})
      addElement(year,'option',{selected:'selected'}).innerText = 'Jump to...'
      year.addEventListener('change',()=>{if(year.selectedIndex==0)return;month.style.display='';month.selectedIndex=-1;month.focus()})
      month.addEventListener('change',()=>{calendar.gotoDate(`${year.selectedOptions[0].value}-${month.value}-01`);year.selectedIndex=0;month.style.display='none'})
      month.addEventListener('blur',()=>{year.selectedIndex=0;month.style.display='none'})
      for (let y=config.span[1];y>=config.span[0];y--) { addElement(year,'option').innerText = String(y) }
      for (const m of ['01Jan','02Feb','03Mar','04Apr','05May','06Jun','07Jul','08Aug','09Sep','10Oct','11Nov','12Dec']) {
        const o = addElement(month,'option',{value:m.slice(0,2),style:'background-color:white;color:black;'}); o.innerText = m.slice(2)
        o.addEventListener('mouseenter',()=>{o.style.filter='invert(100%)'}); o.addEventListener('mouseleave',()=>{o.style.filter='invert(0%)'}) //does not seem to work on Safari
      }
    }
    {
      const sources = header.insertCell()
      const button = addElement(sources,'button',{style:'font-size:x-small;',title:'Click to display the list of event sources'})
      button.innerText = '↓Sources'
      const list = addElement(sources,'div',{style:'font-size:x-small;display:none;position:absolute;z-index:100;'})
      this.sources = {}
      for (const src of config.sources) {
        addElement(list,'div',{style:`border-top:thin solid black;padding:1px;background-color:${src.options.backgroundColor||='black'};color:${src.options.textColor||='white'}`}).innerText = src.id
        this.sources[src.id] = src
      }
      button.addEventListener('click',()=>{list.style.display=''}); button.addEventListener('mouseleave',()=>{list.style.display='none'})
    }

    for (const h of (config.headers||[])) { header.insertCell().innerHTML = h }

    this.getEvents = config.events
    this.processHooks = []
    if (window.Showdown) {
      const conv = new showdown.Converter(window.Showdown)
      this.processHooks.push((details)=>{for(const el of details.getElementsByClassName('transform-markdown')){el.innerHTML = conv.makeHtml(el.textContent)}})
    }
    if (window.MathJax) {
      this.processHooks.push((details)=>{window.MathJax.typeset(Array.from(details.getElementsByClassName('transform-math')))})
    }
    this.processHooks.push(...(config.processHooks||[]))
    this.focus = config.focus||(()=>{})
    this.currentYears = null
    calendar.addEventSource({id:config.id,events:(info)=>this.events(info)})
  }

  events (info) {
    const start = new Date(info.start).getFullYear()
    const end_ = new Date(info.end);end_.setSeconds(end_.getSeconds()-1);const end = end_.getFullYear()
    const years = `${start}-${end}`
    if (this.currentYears==years||this.currentYears=='') {return}
    this.currentYears = ''
    console.log('Loading',years)
    this.calendar.el.style.pointerEvents='none' // avoids bursts of updates, restored after events lookup
    return this.getEvents(start,end)
      .then((data)=>{const events=this.process(data);this.currentYears=years;return events})
      .catch((error)=>{this.el_details.innerHTML=`<pre>${error.message}\n${error.response?error.response.data:''}</pre>`;throw error})
      .finally(()=>{this.calendar.el.style.pointerEvents='auto'})
  }

  process (data) {
    this.el_details.innerHTML = ''
    const events = data.map(row=>this.processRow(row))
    for (const hook of this.processHooks) hook(this.el_details)
    return events
  }

  processRow (row) {
    const ev = {id:`EV-${row.oid}`,start:row.start,end:row.end,title:row.title,extendedProps:{source:row.source}}
    this.el_details.insertAdjacentHTML('beforeend',row.details)
    const tbody = this.el_details.lastElementChild
    tbody.id = ev.id
    const td = tbody.insertRow(0).insertCell()
    td.colSpan = 2; td.className = 'setting'
    const options = this.sources[row.source].options
    Object.assign(ev,options)
    Object.assign(td.style,{backgroundColor:options.backgroundColor,color:options.textColor})
    const extra = tbody.dataset.left||''
    let status = tbody.dataset.right||''
    if (status) {status = `<div class="status">${status}</div>`}
    td.innerHTML = `<span title="${row.access}" style="visibility:${row.access?'visible':'hidden'};style:x-small;">🔒</span>${this.formatSpan(row.start,row.end)} ${extra} ${status}`
    const span = addElement(td,'span',{class:'shadow'})
    span.innerText = '🔗'
    span.addEventListener('click',()=>{this.focus(row.uid)})
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
    const m = t.getMinutes(), h = t.getHours()
    return `${1+((h-1)%12+12)%12}${m?':'+String(m).padStart(2,'0'):''}${h<12?'am':'pm'}` // ugly!
  }
}

function addElement(container,tag,attrs) {
	const el = document.createElement(tag)
	if (attrs) { for (const [k,v] of Object.entries(attrs)) {el.setAttribute(k,v)} }
	container.appendChild(el)
	return el
}
