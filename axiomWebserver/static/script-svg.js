var object, //SVG image from <object />
	SVGDocument //Inner in object 

document.addEventListener('DOMContentLoaded', ready);

function ready() {
	console.log('DOM Loaded!');

	object = document.getElementById('axiom');
	SVGDocument = object.contentDocument;
}

function blink(argument) {
	var pin = SVGDocument.getElementById('ao-0');
	
	try	{
		var pin = document.getElementById("axiom").contentDocument.getElementById("ao-0");
		pin.style.fill = '#fff';
	} catch(err) {
		console.log(pin);
	}
}