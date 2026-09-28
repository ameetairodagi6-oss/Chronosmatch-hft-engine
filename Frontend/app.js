const API = "http://127.0.0.1:8000";


async function updateStatus() {

    try {

        const response = await fetch(`${API}/api/status`);
        const data = await response.json();

        document.getElementById("engine-status").textContent =
            "● " + data.status;

        document.getElementById("orders").textContent =
            data.orders.toLocaleString();

        document.getElementById("trades").textContent =
            data.trades.toLocaleString();

        document.getElementById("throughput").textContent =
            data.throughput.toLocaleString();

        document.getElementById("ipc").textContent =
            data.ipc;

        document.getElementById("best-bid").textContent =
        data.best_bid !== null ? data.best_bid.toFixed(2) : "--";

        document.getElementById("best-ask").textContent =
        data.best_ask !== null ? data.best_ask.toFixed(2) : "--";

        document.getElementById("spread").textContent =
         data.spread !== null ? data.spread.toFixed(2) : "--";

        document.getElementById("encoding").textContent =
            data.encoding;

        document.getElementById("pickle").textContent =
            data.pickle ? "YES" : "NO";

    }

    catch (error) {

        document.getElementById("engine-status").textContent =
            "● DISCONNECTED";

        console.error(error);

    }
}


async function updateOrderBook() {

    try {

        const response = await fetch(`${API}/api/orderbook`);
        const data = await response.json();

        const bids = document.getElementById("bids");
        const asks = document.getElementById("asks");

        bids.innerHTML = "";
        asks.innerHTML = "";


        data.bids.forEach(order => {

            bids.innerHTML += `
                <div class="book-row">
                    <span>${order.price.toFixed(2)}</span>
                    <span>${order.quantity}</span>
                </div>
            `;

        });


        data.asks.forEach(order => {

            asks.innerHTML += `
                <div class="book-row">
                    <span>${order.price.toFixed(2)}</span>
                    <span>${order.quantity}</span>
                </div>
            `;

        });

    }

    catch (error) {
        console.error(error);
    }
}


async function updateTrades() {

    try {

        const response = await fetch(`${API}/api/trades`);
        const data = await response.json();

        const table = document.getElementById("trades-table");

        table.innerHTML = "";

        data.trades.forEach(trade => {

            table.innerHTML += `
                <tr>
                    <td>${trade.time}</td>
                    <td>${trade.side}</td>
                    <td>${trade.price.toFixed(2)}</td>
                    <td>${trade.quantity}</td>
                </tr>
            `;

        });

    }

    catch (error) {
        console.error(error);
    }
}


async function updateBenchmark() {

    try {

        const response = await fetch(`${API}/api/benchmark`);
        const data = await response.json();

        document.getElementById("orders-tested").textContent =
            data.orders_tested.toLocaleString();

        document.getElementById("orders-received").textContent =
            data.orders_received.toLocaleString();

        document.getElementById("orders-lost").textContent =
            data.orders_lost.toLocaleString();

        document.getElementById("benchmark-throughput").textContent =
            data.throughput.toLocaleString();

    }

    catch (error) {
        console.error(error);
    }
}


async function updateDashboard() {

    await updateStatus();
    await updateOrderBook();
    await updateTrades();
    await updateBenchmark();

}


updateDashboard();

setInterval(updateDashboard, 1000);