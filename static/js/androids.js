(function ($) {
	
	$(document).ready(function () {
		
		var platform = location.search.substr(1).split('=')[1],
			$form    = $("form");
		
		function insertDates(start, end) {
		    $('#startDate').text(start);
    		$('#endDate').text(end);
		}
		
		/**
		 * Insert return data on successful date submission.
		 * @static
		 * data {Object} 
		 */
		function done(data) {
			insertDates(data.dates.startDate, data.dates.endDate);
			
			var tbl = $("#results");
			
			// insert data into upper table
            for (var i = 0; i < data.testTypes.length; i++) {
                var result = data.byTest[data.testTypes[i]];

                for (var j = 0; j < $results.rows.length; j++) {
                    row = tbl.rows[j];
                    cell = row.insertCell(i+1);
                    textNode = j==0 ? testTypes[i] : result[row.id];
                    cell.innerHTML = textNode;
                }
            }
			
		}
		
		function fail(error) {
			
		}
		
		function fetchData(e) {
			if (e) e.preventDefault();
			$.getJSON("/data/platform/", $form.serialize()).done(done).fail(fail);
		}
		
		$form.append("<input type='hidden' name='platform' value='%s' />".replace("%s", platform)).submit(fetchData);
	});
	
})(jQuery);

