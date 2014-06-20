// This function is used to get the data for all platforms from the python webserver.
function getData(platforms) {
    var data_platform = {};
    var json_data = $('#form-datechoices').serialize();

    // Sending a synchronous get request because JS has to proceed to the next statement only after this request is completed as the data for all platforms is required for the graph to be plotted successfully.
    $.ajax({
        url: '/data/results/flot/day',
        type: 'get',
        dataType: 'json',
        data: json_data,
        async: false,
        success: function(data) {
            data_platform = data;
        }
    });
    return data_platform;
}

// This function is used to convert the data obtained from getData into a format required by flot.
function getDataSets(data) {
    var datasets = {};

    $.each(data,function(platformName,platformValue) {
        datasets[platformName] = {};
        datasets[platformName].label = platformName;

        var failures = {
            color: 'orange',
            data: platformValue.data.failures,
            label: 'failures' + '-' + platformName,
            lines: { show: true, color: 'orange'},
            yaxis: 2
        };
        var totals = {
            color: 'blue',
            data: platformValue.data.totals,
            label: 'total jobs' + '-' + platformName,
            lines: {show: true, color: 'blue'},
        };

        datasets[platformName].data = [totals, failures];
    })

    return datasets;
}
