$(document).on({
  ajaxStart: function() {
    $('form input[type="submit"]').attr('disabled', true);
    $('body').addClass('loading');
    },
  ajaxStop: function() {
    $('form input[type="submit"]').attr('disabled', false);
    $('body').removeClass('loading');
    }
  });


$(function() {
  fetchData();
});


$(function() {
  $('form').submit(function (e) {
    e.preventDefault();
    fetchData();
  });
});


$(function() {
  $('#showHidden').click(
    showHidden);
});


function showHidden() {
  $('.hidden').toggle(
    $('#showHidden').is(':checked'));
}


function fetchData(queryString) {
  $('#error').hide();
  var qs = $('form').serialize();
  $.getJSON('/data/slaves/', qs)
    .done(insertData)
    .fail(function () {
      var errMsg = 'Ajax request failed';
      handleError(errMsg);
    });
}


function handleError(errMsg) {
  $('.reportDates').hide();
  clearResultsTable();
  $('#error').text(errMsg).show();
}


function clearResultsTable() {
  var rows = $('#results tr').slice(1);
  if (rows.length > 0) {
    rows.remove();
  }
}


function insertDates(dates) {
  $('.reportDates').show();
  $('#startDate').text(dates.startDate);
  $('#endDate').text(dates.endDate);
}


function insertData(json) {
  // handling errors in response
  if (json.error) {
    handleError(json.error);
    return;
  }

  var slaves_data = json.slaves,
      platform_data = json.platforms,
      dates = json.dates,
      info = json.disclaimer;

  // insert dates
  insertDates(dates);

  // insert disclaimer
  $('#info').text(info);

  // globally used variables
  var tbl = $('#results');
  var columns = getTableColumns();

  // remove rows from table
  clearResultsTable();

  // default sorting by total runs desc
  var to_sort = [];
  $.each(slaves_data, function(index, object) {
      to_sort.push({key: index, value: object.total});
  });
  to_sort.sort(function(x, y) {return y.value - x.value});

  // get slaves data (sorted)
  $.each(to_sort, function(index, value) {
    var results = slaves_data[value.key];
    results['slave'] = value.key;

    // get platform failure rate
    $.each(platform_data, function(index, value) {
      var re = RegExp("^" + index + "-.*");
      if (results['slave'].match(re) !== null) {
        results['pfr'] = value;
      }
    });

    // insert rows
    var row = $('<tr></tr>')
      .addClass(
        (results['success'] == results['total'] ? 'hidden' : ''));

    $.each(columns, function(i, v) {
      var cell = $('<td></td>');
      if (v == 'sfr' || v == 'pfr') {
        cell.attr('data-no-retries', results[v]['failRate']);
        cell.attr('data-with-retries', results[v]['failRateWithRetries']);
      } else {
        cell.text(results[v]);
      }

      row.append(cell);

    });

    tbl.append(row);

  });

  // display hidden rows if related checkbox is checked
  showHidden();

  // populate sfr and pfr columns
  switchFailRates();

  // make table sortable
  sorttable.makeSortable(tbl[0]);

}


function switchFailRates() {
  var isChecked = $('#includeRetries').is(':checked');
  var attrToUse = isChecked === true ? 'withRetries' : 'noRetries';

  var tblRows = $('#results').find('tr').slice(1);
  var labels = getTableColumns();
  var sfrIndex = labels.indexOf('sfr');
  var pfrIndex = labels.indexOf('pfr');

  $(tblRows).each(function() {
    var sfrCell = $(this.cells[sfrIndex]);
    var pfrCell = $(this.cells[pfrIndex]);
    var sfr = sfrCell.data(attrToUse);
    var pfr = pfrCell.data(attrToUse);

    sfrCell.text(sfr);
    pfrCell.text(pfr);

    if (sfr > pfr) {
      sfrCell.addClass('alert');
    } else {
      sfrCell.removeClass('alert');
    }
  });
}


function getTableColumns() {
  var labels = [];
  $('.headrow td').each(function() {
    labels.push(this.dataset['type']);
  });
  return labels;
}
