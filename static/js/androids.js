(function ($) {

    $(document).ready(function () {

        var platform = location.search.substr(1).split('=')[1],
            title    = title = platform.charAt(0).toUpperCase() + platform.substr(1),
            $form    = $("form"),
            $error   = $("#error"),
            $dates   = $(".reportDates"),
            $body    = $("body");

        document.title = "Ouija | " + title + " Failure Rate";

        var headerElem = document.createElement('h1');
        headerElem.innerHTML = title;

        var pageHeader = document.getElementById("pageHeader");
        pageHeader.insertBefore(headerElem, pageHeader.firstChild);

        function clearTables(fn) {
            var tr  = $("#results tr");

            for (var i = 0, n = tr.length; i < n; i++) {
                for (var j = 1, k = tr[i].children.length; j < k; j++)
                    $(tr[i].children[j]).remove();
            }

            tr = $("#green_results tr");

            for (var i = 0, n = tr.length; i < n; i++) {
                if (i == 0) {
                    for (var j = tr[i].children.length; j !== 0; j--)
                        $(tr[i].children[j]).remove();
                } else {
                    $(tr[i]).remove();
                }
            }

            fn();
        }

        /**
         * @param start
         * @param end
         */
        function renderDates(start, end) {
            document.getElementById('startDate').innerHTML = start;
            document.getElementById('endDate').innerHTML = end;
        }

        /**
         * Insert data into upper table.
         * @param testTypes
         * @param testResults
         * @param failRates
         */
        function renderResults(testTypes, testResults, failRates) {
            var tbl = document.getElementById('results');

            for (var i = 0; i < testTypes.length; i++) {
                var result = testResults[testTypes[i]], row, cell, textNode;

                for (var j = 0; j < tbl.rows.length; j++) {
                    row  = tbl.rows[j],
                    cell = row.insertCell(i+1),
                    textNode = (j == 0) ? testTypes[i] : result[row.id];
                    cell.innerHTML = textNode;
                }
            }

            // fill failure rates
            document.getElementById('failure_rate').innerHTML = failRates['failRateWithRetries'];
            document.getElementById('failure_exclude_retry').innerHTML = failRates['failRate'];

            sorttable.makeSortable(tbl);
        }

        /**
         * @param testTypes
         * @param revisionResults
         */
        function renderRevisions(testTypes, revisionResults) {
            var tbl = document.getElementById('green_results'), row, cell, textNode;

            // remove total and percentage stats
            testTypes.splice(-2, 2);

            // insert revisions into lower table
            for (var revision in revisionResults) {
                row = tbl.insertRow(-1);
                (row.insertCell(0)).innerHTML = revisionResults[revision].cset_id;
            }

            // insert data into lower table
            for (var i=0; i < testTypes.length; i++) {
                var test = testTypes[i];

                for (var j=0; j<tbl.rows.length; j++) {
                    cell = tbl.rows[j].insertCell(-1);

                    // TODO: remove this...
                    if (j == 0) {
                        textNode = testTypes[i];
                    } else {
                        textNode = (revisionResults[j-1] === undefined) ? 0 : (revisionResults[j-1].green[test] || 0);
                    }
                    // TODO: put this back...
                    //textNode = (j == 0) ? testTypes[i] : (revisionResults[j-1].green[test] || 0);
                    cell.innerHTML = textNode;
                }
            }

            sorttable.makeSortable(tbl);
        }

        function done(data) {
            if ($error.is(":visible")) $error.hide();
            $dates.show();

            clearTables(function () {
                console.info("rendering results...");

                renderDates(data.dates.startDate, data.dates.endDate);
                renderResults(data.testTypes, data.byTest, data.failRates);
                renderRevisions(data.testTypes, data.byRevision);

                var tr = $("#green_results tr");

                setTimeout(function () {

                }, 2000)

            });
        }

        function fail(error) {
            $dates.hide();
            $error.text(error).show();
        }

        function fetchData(e) {
            if (e) e.preventDefault();
            $.getJSON("/data/platform/", $form.serialize()).done(done).fail(fail);
        }

        $form.append("<input type='hidden' name='platform' value='%s' />".replace("%s", platform)).submit(fetchData);

        $(document).on("ajaxStart ajaxStop", function (e) {
            (e.type === "ajaxStart") ? $body.addClass("loading") : $body.removeClass("loading");
        });

        fetchData();
    });

})(jQuery);

