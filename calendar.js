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
      month.addEventListener('blur',()=>{year.selectedIndex=0;month.style.display='none'})
      for (let y=config.span[1];y>=config.span[0];y--) {
        const o = addElement(year,'option')
        o.innerText = String(y)
        o.addEventListener('click',()=>{month.style.display='';month.selectedIndex=-1;month.focus()})
      }
      ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'].forEach((m,i)=>{
        const o = addElement(month,'option',{value:String(i+1).padStart(2,'0'),style:'background-color:white;color:black;'})
        o.innerText = m
        o.addEventListener('mouseenter',()=>{o.style.filter='invert(100%)'})
        o.addEventListener('mouseleave',()=>{o.style.filter='invert(0%)'})
        o.addEventListener('click',()=>{calendar.gotoDate(`${year.selectedOptions[0].value}-${o.value}-01`);year.selectedIndex=0;month.style.display='none'})
      })
    }
    {
      header.insertCell().innerHTML = '<span> Sources: </span>'
      this.sources = Object.fromEntries(config.sources.map((src)=>{
        const td = header.insertCell(); td.innerHTML = src.id
        td.style.backgroundColor = src.options.backgroundColor ||= 'black'
        td.style.color = src.options.textColor ||= 'white'
        return [src.id,src]
      }))
    }

    for (const h of (config.headers||[])) { header.insertCell().innerHTML = h }

    this.getEvents = config.events

    if (window.Showdown) {
      const conv = new showdown.Converter(window.Showdown)
      this.transformMarkdown = (a) => {for(const el of a){el.innerHTML = conv.makeHtml(el.innerHTML)}}
    }
    if (window.MathJax) {
      this.transformMath = (a) => {if(a.length)window.MathJax.typeset(a)}
    }
    this.currentYears = null
    calendar.addEventSource({id:config.id,events:(info,success,failure)=>this.events(info,success,failure)})
  }

  events (info,success,failure) {
    const start = new Date(info.start).getFullYear()
    const end_ = new Date(info.end);end_.setSeconds(end_.getSeconds()-1);const end = end_.getFullYear()
    const years = `${start}-${end}`
    if (this.currentYears==years||this.currentYears=='') {return}
    this.calendar.el.style.pointerEvents='none' // avoids bursts of updates, restored after events lookup
    this.currentYears = ''
    console.log('Loading',years)
    this.getEvents(start,end)
      .then((data)=>{success(this.process(data));this.currentYears=years})
      .catch((error)=>{failure(error);this.el_details.innerHTML=`<pre>${error.message}\n${error.response?error.response.data:''}</pre>`})
      .finally(()=>{this.calendar.el.style.pointerEvents='auto'})
  }

  process (data) {
    this.el_details.innerHTML = ''
    const events = data.map((row)=>this.processRow(row))
    if (this.transformMarkdown) { this.transformMarkdown(Array.from(this.el_details.getElementsByClassName('transform-markdown'))) }
    if (this.transformMath) { this.transformMath(Array.from(this.el_details.getElementsByClassName('transform-math'))) }
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
    for (const o in options) { ev[o] = options[o] }
    td.style.backgroundColor = options.backgroundColor
    td.style.color = options.textColor
    const extra = tbody.dataset.left||''
    let status = tbody.dataset.right||''
    if (status) {status = `<div class="status">${status}</div>`}
    td.innerHTML = `<span title="${row.access}" style="visibility:${row.access?'visible':'hidden'};style:x-small;">🔒</span>${this.formatSpan(row.start,row.end)} ${extra} ${status}`
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

function addElement(container,tag,attrs) {
	const el = document.createElement(tag)
	if (attrs) { for (const [k,v] of Object.entries(attrs)) {el.setAttribute(k,v)} }
	container.appendChild(el)
	return el
}
