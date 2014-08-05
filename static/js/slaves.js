$(function() {
  var $form = $("form"),
      $body = $("body"),
      $info = $("#info"),
      $error = $("#error"),
      $dates = $(".reportDates"),
      $table = $("#results"),
      tableColumns = ["slave", "fail", "retry", "infra", "success",
                       "total", "sfr", "pfr", "jobs_since_last_success"],
      slaveURL = "https://secure.pub.build.mozilla.org/builddata/reports/slave_health/slave.html?name=";

  function fetchData(e) {
    if (e) e.preventDefault();
    $.getJSON("/data/slaves/", $form.serialize())
      .done(renderResponse)
      .fail(handleError);
  }

  function renderResponse(data) {
    if (data.error) {
      handleError(data.error);
      return;
    }

    if ($error.is(":visible")) $error.hide();

    renderDates(data.dates.startDate, data.dates.endDate);
    renderDisclaimer(data.disclaimer);
    renderResults(data.slaves, data.platforms);
  }

  function handleError(errMsg) {
    if ($.type(errMsg) === "object") {
      errMsg = "Ajax request failed";
    }
    $dates.hide();
    $info.hide();
    clearResultsTable();
    $error.text(errMsg).show();
  }

  function renderDates(start, end) {
    $dates.show();
    $("#startDate").text(start);
    $("#endDate").text(end);
  }

  function renderDisclaimer(text) {
    $info.show();
    $info.text(text);
  }

  function renderResults(slaves, platforms) {
    clearResultsTable();
    populateResultsTable(slaves, platforms);
    showHidden();
    switchFailRates();
    applySorting();
  }

  function clearResultsTable() {
    var rows = $table.find("tr").slice(1);
    if (rows.length > 0) {
      rows.remove();
    }
  }

  function populateResultsTable(slaves, platforms) {
    $.each(slaves, function(index, value) {
      var stats = slaves[index];
      stats["slave"] = index;

      $.each(platforms, function(index, value) {
        if (stats["slave"].match(RegExp("^" + index + "-.*")) !== null) {
          stats["pfr"] = value;
          return false;
        }
      });

      var row = $("<tr></tr>").addClass(
          (stats["success"] == stats["total"] ? "hidden" : ""));

      $.each( tableColumns, function(i, v) {
        var cell = $("<td></td>");

        if (v == "slave") {
          var slave_name = stats[v],
              link = $("<a></a>", {
                text: slave_name,
                target: "_blank",
                href: slaveURL + slave_name
              });
          cell.append(link);
        }

        else if (v == "sfr" || v == "pfr") {
          cell.attr("data-no-retries", stats[v]["failRate"]);
          cell.attr("data-with-retries", stats[v]["failRateWithRetries"]);
        }

        else {
          cell.text(stats[v]);
        }

        row.append(cell);
      });

      $table.append(row);
    });
  }

  function switchFailRates() {
    var attrToUse = $("#includeRetries").is(":checked") === true ? "withRetries" : "noRetries",
        tblRows = $table.find("tr").slice(1),
        sfrIndex =  tableColumns.indexOf("sfr"),
        pfrIndex =  tableColumns.indexOf("pfr");

    $(tblRows).each(function() {
      var sfrCell = $(this.cells[sfrIndex]),
          pfrCell = $(this.cells[pfrIndex]),
          sfr = sfrCell.data(attrToUse),
          pfr = pfrCell.data(attrToUse);

      sfrCell.text(Number(sfr).toFixed(1));
      pfrCell.text(Number(pfr).toFixed(1));

      sfrCell.toggleClass("alert", sfr > pfr);
    });

    applySorting();
  }

  function sortedBy() {
    var headers = $table.find("th"),
        sorting = [];

    $.each(headers, function(index, header) {
      if ($(header).hasClass("headerSortUp")) {
        sorting[sorting.length] = [index, 1];
      }
      else if ($(header).hasClass("headerSortDown")) {
        sorting[sorting.length] = [index, 0];
      }
    });
    return sorting;
  }

  function applySorting() {
    var sorting = sortedBy();

    // if table is not sorted, then use default sorting by total jobs desc
    if (sorting.length === 0) {
      sorting[0] = [tableColumns.indexOf("total"), 1];
    }

    $table.trigger("update");

    setTimeout(function() {
      $table.trigger("sorton", [sorting]);
      }, 1000);
  }

  function showHidden() {
    $(".hidden").toggle($("#showHidden").is(":checked"));
  }

  $dates.hide();
  $form.submit(fetchData);
  $("#showHidden").change(showHidden);
  $("#includeRetries").change(switchFailRates);
  $table.tablesorter();

  $(document).on("ajaxStart ajaxStop", function (e) {
      (e.type === "ajaxStart") ? $body.addClass("loading") : $body.removeClass("loading");
  });

  fetchData();

});
