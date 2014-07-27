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
  function fetchData() {
    var qs = $('form').serialize();
    $('#error').hide();

    $.getJSON('/data/slaves/', qs)
      .done(function(json) {
        insertData(json);
      })
      .fail(function() {
        handleError('Ajax request failed');
      });
  }

  function handleError(errMsg) {
    $('.reportDates').hide();
    clearResultsTable();
    $('#error').text(errMsg).show();
  }

  function getTableColumns() {
    var labels = [];
    $('.headrow td').each(function() {
      labels.push(this.dataset['type']);
    });
    return labels;
  }

  function clearResultsTable() {
    var rows = $('#results tr').slice(1);
    if (rows.length > 0) {
      rows.remove();
    }
  }

  function showHidden() {
    $('.hidden').toggle($('#showHidden').is(':checked'));
  }

  function switchFailRates() {
    var attrToUse = $('#includeRetries').is(':checked') === true ? 'withRetries' : 'noRetries',
        tblRows = $('#results').find('tr').slice(1),
        labels = getTableColumns(),
        sfrIndex = labels.indexOf('sfr'),
        pfrIndex = labels.indexOf('pfr'),
        sfrHead = $('.headrow td')[sfrIndex],
        pfrHead = $('.headrow td')[pfrIndex];

    $(tblRows).each(function() {
      var sfrCell = $(this.cells[sfrIndex]),
          pfrCell = $(this.cells[pfrIndex]),
          sfr = sfrCell.data(attrToUse),
          pfr = pfrCell.data(attrToUse);

      sfrCell.text(sfr);
      pfrCell.text(pfr);

      if (sfr > pfr) {
        sfrCell.addClass('alert');
      } else {
        sfrCell.removeClass('alert');
      }
    });

    // monkey patch for sorting
    applySortIfNeeded(sfrHead);
    applySortIfNeeded(pfrHead);
  }

  function applySortIfNeeded(columnHead) {
    if (columnHead.className.search('sorttable_sorted') != -1) {
      var classes = columnHead.className.split(' ');
      columnHead.className = classes[0];
      sorttable.innerSortFunction.apply(columnHead, []);

      if (classes[1].search('reverse') != -1) {
        sorttable.innerSortFunction.apply(columnHead, []);
      }
    }
  }

  function populateResultsTable(slaves, platforms) {
    var tbl = $('#results'),
        columns = getTableColumns();

    // default sorting is by total runs desc
    var sorted = [];
    $.each(slaves, function(index, object) {
        sorted.push({key: index, value: object.total});
    });

    sorted.sort(function(x, y) {
      return y.value - x.value;
    });

    // get slaves data (sorted)
    $.each(sorted, function(index, value) {
      var results = slaves[value.key];
      results['slave'] = value.key;

      // get platform failure rate
      $.each(platforms, function(index, value) {
        if (results['slave'].match(RegExp("^" + index + "-.*")) !== null) {
          results['pfr'] = value;
          return false;
        }
      });

      // insert rows
      var row = $('<tr></tr>').addClass(
          (results['success'] == results['total'] ? 'hidden' : ''));

      $.each(columns, function(i, v) {
        var cell = $('<td></td>');

        if (v == 'slave') {
          var slave_name = results[v],
              link = $('<a>', {
                text: slave_name,
                target: '_blank',
                href: 'https://secure.pub.build.mozilla.org/builddata/reports/slave_health/slave.html?name=' + slave_name
              });
          cell.append(link);
        }

        else if (v == 'sfr' || v == 'pfr') {
          cell.attr('data-no-retries', Number(results[v]['failRate']).toFixed(1));
          cell.attr('data-with-retries', Number(results[v]['failRateWithRetries']).toFixed(1));
        }

        else {
          cell.text(results[v]);
        }

        row.append(cell);
      });

      tbl.append(row);
    });
  }

  function insertDates(dates) {
    $('.reportDates').show();
    $('#startDate').text(dates.startDate);
    $('#endDate').text(dates.endDate);
  }

  function insertData(json) {
    var slaves_data = json.slaves,
        platform_data = json.platforms,
        dates = json.dates,
        info = json.disclaimer,
        error = json.error;

    // handle error in server response
    if (json.error) {
      handleError(json.error);
      return;
    }

    // insert dates
    insertDates(dates);

    // insert disclaimer
    $('#info').text(info);

    // remove rows from table
    clearResultsTable();

    // populate table
    populateResultsTable(slaves_data, platform_data);

    // display hidden rows if related checkbox is checked
    showHidden();

    // populate sfr and pfr columns
    switchFailRates();
  }

  $('form').submit(function (e) {
    e.preventDefault();
    fetchData();
  });

  $('#showHidden').change(showHidden);

  $('#includeRetries').change(switchFailRates);

  fetchData();

  sorttable.makeSortable($('#results')[0]);
});
