$(function() {
  var platform = location.search.substr(1).split('=')[1],
      title    = platform.charAt(0).toUpperCase() + platform.substr(1),
      $form    = $("form"),
      $error   = $("#error"),
      $dates   = $(".reportDates"),
      $body    = $("body");

  document.title = "Ouija | " + title + " Failure Rate";
  $("#pageHeader h1").text(title);

  function clearTables(fn) {
    var tr = $("#results tr"), i, j;

    for (i = 0; i < tr.length; i++) {
      for (j = tr[i].children.length; j !== 0; j--)
        $(tr[i].children[j]).remove();
      }

    tr = $("#greenResults tr");

    for (i = 0; i < tr.length; i++) {
      if (i === 0) {
        for (j = tr[i].children.length; j !== 0; j--)
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
    $dates.show();
    $('#startDate').text(start);
    $('#endDate').text(end);
  }

  /**
   * Insert data into upper table.
   * @param testTypes
   * @param testResults
   * @param failRates
   */
  function renderResults(testTypes, testResults, failRates) {
    var table = $("#results"),
        rows = table.find("tr");

    $.each(testTypes, function(testIndex, testType) {
      var result = testResults[testType], cell;

      $.each(rows, function(index, row) {
        if (index === 0) {
          cell = $("<th></th>").text(testTypes[testIndex]);
        }
        else {
          cell = $("<td></td>").text(result[row.id]);
        }
        $(row).append(cell);
      });
    });

    table.tablesorter();

    // fill failure rates
    $('#withRetry').text(failRates['failRateWithRetries'] + "%");
    $('#excludeRetry').text(failRates['failRate'] + "%");
  }

  /**
   * @param testTypes
   * @param revisionResults
   */
  function renderRevisions(testTypes, revisionResults) {
    var table = $('#greenResults'),
        cell;

    // remove total and percentage stats
    testTypes.splice(-2, 2);

    // insert revisions into lower table
    $.each(revisionResults, function(i, revision) {
      table.append("<tr><td>" + revision.cset_id + "</td></tr>");

      // insert data into lower table
      $.each(testTypes, function(testIndex, testType) {
        table.find("tr").each(function(index) {
          if (index === 0) {
            cell = $("<th></th>").text(testType);
          }
          else {
            cell = $("<td></td>").text(revisionResults[index -1].green[testType] || 0);
          }
          $(this).append(cell);
        });
      });
    });

    table.tablesorter();

  }

  function done(data) {
    if ($error.is(":visible")) $error.hide();

    clearTables(function () {
      if (!data.dates) {
        data.dates = {
          "startDate": "",
          "endDate": ""
        };
      }
      renderDates(data.dates.startDate, data.dates.endDate);
      renderResults(data.testTypes, data.byTest, data.failRates);
      renderRevisions(data.testTypes, data.byRevision);
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

  $("input[name='platform']").val(platform);
  $form.submit(fetchData);

  $(document).on("ajaxStart ajaxStop", function (e) {
    (e.type === "ajaxStart") ? $body.addClass("loading") : $body.removeClass("loading");
  });

  fetchData();

});
