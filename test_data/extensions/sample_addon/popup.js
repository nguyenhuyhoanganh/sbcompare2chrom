let n = 0;
document.getElementById('count').onclick = e => { n++; e.target.textContent = 'Clicked ' + n; };
